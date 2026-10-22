"""Local MyRewards catalogue, wallet entities, and redemption rules."""

import json
import logging
import math
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

log = logging.getLogger(f"app.{__name__}")
CATALOG_PATH = Path(__file__).with_name("reward_catalog.json")


@dataclass
class User:
    id: str
    name: str
    pointsBalance: int


@dataclass
class Reward:
    id: str
    brand: str
    title: str
    description: str
    imageUrl: str
    pointsCost: int
    valueLabel: str
    category: str
    validDays: int
    termsList: list[str]
    restrictions: list[str]
    active: bool
    logoUrl: str | None = None


@dataclass
class Voucher:
    id: str
    userId: str
    rewardId: str
    status: str
    redeemedAt: str
    validTill: str
    qrToken: str | None = None
    qrExpiresAt: str | None = None
    usedAt: str | None = None


@dataclass
class PointsTransaction:
    id: str
    userId: str
    type: str
    points: int
    refId: str
    createdAt: str


def load_catalog():
    """Read the editable seed catalogue shipped with the app."""
    with CATALOG_PATH.open(encoding="utf-8") as catalog_file:
        catalog = json.load(catalog_file)
    catalog["rewards"] = [asdict(Reward(**reward)) for reward in catalog.get("rewards", [])]
    return catalog


def new_state(user_id, user_name, points_balance):
    return {
        "user": asdict(User(str(user_id), user_name or "Member", max(0, int(points_balance)))),
        "vouchers": [],
        "pointsTransactions": [],
        "localPointsSpent": 0,
        "usedPromoCodes": [],
    }


def ensure_state(state, user_id, user_name, points_balance):
    state.setdefault("user", asdict(User(str(user_id), user_name or "Member", max(0, int(points_balance)))))
    state.setdefault("vouchers", [])
    state.setdefault("pointsTransactions", [])
    state.setdefault("localPointsSpent", 0)
    state.setdefault("usedPromoCodes", [])
    state["user"]["id"] = str(user_id)
    state["user"]["name"] = user_name or state["user"].get("name", "Member")
    state["user"]["pointsBalance"] = available_points(state, points_balance)
    expire_vouchers(state)
    return state


def available_points(state, account_balance):
    """Return the authoritative points balance loaded from Supabase."""
    return max(0, int(account_balance or 0))


def expire_vouchers(state, today=None):
    today = today or date.today()
    for voucher in state.get("vouchers", []):
        if voucher.get("status") == "active":
            try:
                if date.fromisoformat(voucher["validTill"]) < today:
                    voucher["status"] = "expired"
                    voucher["qrToken"] = None
                    voucher["qrExpiresAt"] = None
            except (KeyError, TypeError, ValueError):
                voucher["status"] = "expired"
    return state


def reward_for(catalog, reward_id):
    return next((reward for reward in catalog["rewards"] if reward["id"] == reward_id), None)


def has_redeemed_reward(state, reward_id):
    """Return whether this member has ever received a voucher for this reward."""
    user_id = str(state.get("user", {}).get("id", ""))
    return any(
        str(voucher.get("userId", user_id)) == user_id
        and str(voucher.get("rewardId")) == str(reward_id)
        for voucher in state.get("vouchers", [])
    )


def merge_cloud_vouchers(state, cloud_vouchers):
    """Merge the member's shared Supabase voucher history into local state."""
    vouchers = state.setdefault("vouchers", [])
    by_id = {str(item.get("id")): item for item in vouchers}
    transactions = state.setdefault("pointsTransactions", [])
    transaction_refs = {str(item.get("refId")) for item in transactions}

    for record in cloud_vouchers or []:
        voucher_id = str(record.get("id", ""))
        reward_id = str(record.get("rewardId", ""))
        if not voucher_id or not reward_id:
            continue
        points_spent = max(0, int(record.get("pointsSpent", 0) or 0))
        voucher = {
            "id": voucher_id,
            "userId": str(record.get("userId", state.get("user", {}).get("id", ""))),
            "rewardId": reward_id,
            "status": record.get("status", "active"),
            "redeemedAt": record.get("redeemedAt", ""),
            "validTill": str(record.get("validTill", "")),
            "qrToken": record.get("qrToken"),
            "qrExpiresAt": record.get("qrExpiresAt"),
            "usedAt": record.get("usedAt"),
        }
        current = by_id.get(voucher_id)
        if current is None:
            vouchers.append(voucher)
            by_id[voucher_id] = voucher
        else:
            current.update({key: value for key, value in voucher.items() if value is not None})

        if points_spent and voucher_id not in transaction_refs:
            transaction = asdict(PointsTransaction(
                id=f"cloud-{voucher_id}",
                userId=voucher["userId"],
                type="redeem",
                points=points_spent,
                refId=voucher_id,
                createdAt=voucher["redeemedAt"],
            ))
            transactions.append(transaction)
            transaction_refs.add(voucher_id)

    # Supabase's points_ledger is authoritative and already includes voucher debits.
    state["localPointsSpent"] = 0
    return state


def redeem_reward(state, reward, account_balance, now=None, cloud_voucher=None):
    """Deduct points and issue a voucher, using the shared server voucher when provided."""
    if not reward or not reward.get("active"):
        return None, "This reward is no longer available."
    if has_redeemed_reward(state, reward.get("id")):
        return None, "You have already redeemed this reward."
    balance = available_points(state, account_balance)
    cost = int(reward["pointsCost"])
    if balance < cost:
        return None, f"You need {cost - balance} more points to redeem this reward."

    now = now or datetime.now().astimezone()
    voucher = asdict(Voucher(
        id=str(uuid.uuid4()),
        userId=state["user"]["id"],
        rewardId=reward["id"],
        status="active",
        redeemedAt=now.isoformat(),
        validTill=(now.date() + timedelta(days=int(reward.get("validDays", 30)))).isoformat(),
    ))
    transaction = asdict(PointsTransaction(
        id=str(uuid.uuid4()),
        userId=state["user"]["id"],
        type="redeem",
        points=cost,
        refId=voucher["id"],
        createdAt=now.isoformat(),
    ))
    state["localPointsSpent"] = int(state.get("localPointsSpent", 0)) + cost
    state["user"]["pointsBalance"] = max(0, balance - cost)
    state["vouchers"].insert(0, voucher)
    state["pointsTransactions"].insert(0, transaction)
    log.info("Issued local voucher %s for reward %s", voucher["id"], reward["id"])
    return voucher, ""


def add_promo_voucher(state, catalog, code, now=None):
    code = (code or "").strip().upper()
    reward_id = catalog.get("promoCodes", {}).get(code)
    if not reward_id:
        return None, "That promo code was not recognized."
    if code in state.get("usedPromoCodes", []):
        return None, "This promo code has already been used."
    reward = reward_for(catalog, reward_id)
    if not reward or not reward.get("active"):
        return None, "The reward for this promo code is unavailable."
    now = now or datetime.now().astimezone()
    voucher = asdict(Voucher(
        id=str(uuid.uuid4()),
        userId=state["user"]["id"],
        rewardId=reward["id"],
        status="active",
        redeemedAt=now.isoformat(),
        validTill=(now.date() + timedelta(days=int(reward.get("validDays", 30)))).isoformat(),
    ))
    state["vouchers"].insert(0, voucher)
    state.setdefault("usedPromoCodes", []).append(code)
    return voucher, f"Promo applied — {reward['title']} added to My Vouchers."


def activate_qr(voucher, now=None):
    if voucher.get("status") != "active":
        return None, "This voucher is no longer active."
    now = now or datetime.now().astimezone()
    try:
        if date.fromisoformat(voucher["validTill"]) < now.date():
            voucher["status"] = "expired"
            return None, "This voucher has expired."
    except (KeyError, TypeError, ValueError):
        voucher["status"] = "expired"
        return None, "This voucher has expired."
    token = f"FAMI-{uuid.uuid4().hex[:12].upper()}"
    voucher["qrToken"] = token
    voucher["qrExpiresAt"] = (now + timedelta(minutes=5)).isoformat()
    return token, ""


def qr_seconds_remaining(voucher, now=None):
    if not voucher or not voucher.get("qrExpiresAt"):
        return 0
    try:
        expiry = datetime.fromisoformat(voucher["qrExpiresAt"])
        now = now or datetime.now().astimezone()
        return max(0, math.ceil((expiry - now).total_seconds()))
    except (TypeError, ValueError):
        return 0


def mark_voucher_used(state, voucher, now=None):
    if not voucher or voucher.get("status") != "active":
        return False
    if qr_seconds_remaining(voucher, now) <= 0:
        return False
    now = now or datetime.now().astimezone()
    voucher["status"] = "used"
    voucher["usedAt"] = now.isoformat()
    voucher["qrExpiresAt"] = now.isoformat()
    return True
