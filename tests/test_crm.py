"""Тесты CRM: сертификаты, бонусы за визит, фильтры клиентов, автоматизации, сотрудники. Нужна БД с демо-данными."""
import asyncio
import uuid
from datetime import timedelta

import pytest

from app import automations, booking, certificates, db, loyalty, staff


async def _with_pool(coro_fn):
    await db.open_pool()
    try:
        return await coro_fn()
    finally:
        await db.close_pool()


def test_certificate_sale_and_partial_redeem():
    async def scenario():
        number = "TEST-" + uuid.uuid4().hex[:6].upper()
        cert = await certificates.issue(number, 5000, buyer_name="Тест")
        after = await certificates.redeem(number, 3000, actor="тест")
        with pytest.raises(ValueError):
            await certificates.redeem(number, 2500)  # больше остатка
        final = await certificates.redeem(number, 2000)
        with pytest.raises(ValueError):
            await certificates.redeem(number, 1)  # уже использован
        return cert["balance"], after["balance"], final["status"], [o["kind"] for o in final["ops"]]

    start, middle, status, ops = asyncio.run(_with_pool(scenario))
    assert (start, middle, status) == (5000, 2000, "used")
    assert ops == ["sale", "redeem", "redeem"]


def test_duplicate_certificate_number_rejected():
    async def scenario():
        number = "TEST-" + uuid.uuid4().hex[:6].upper()
        await certificates.issue(number, 1000)
        with pytest.raises(ValueError):
            await certificates.issue(number, 1000)
        return True

    assert asyncio.run(_with_pool(scenario))


def test_visit_accrues_cashback_and_limits_bonus_payment():
    async def scenario():
        bk = await db.query_one(
            "SELECT b.id, b.guest_id, b.price_total FROM bookings b WHERE b.status = 'confirmed' ORDER BY b.id DESC LIMIT 1"
        )
        await db.query("DELETE FROM bonus_tx WHERE booking_id = %s RETURNING id", (bk["id"],))
        await loyalty.add_bonus(bk["guest_id"], 100000, "adjust", "тест")
        result = await loyalty.mark_visit(bk["id"], True, paid=10000, bonus_spent=90000)
        again = await loyalty.accrue_for_visit(bk["id"], bk["guest_id"], 10000, "gold")
        await db.query("DELETE FROM bonus_tx WHERE booking_id = %s OR (guest_id = %s AND note LIKE 'тест%%') RETURNING id", (bk["id"], bk["guest_id"]))
        await loyalty.add_bonus(bk["guest_id"], 0, "adjust", "тест: пересчёт баланса")
        await db.query("UPDATE bookings SET status = 'confirmed', paid_amount = NULL, bonus_spent = 0 WHERE id = %s RETURNING id", (bk["id"],))
        return result, again, bk["price_total"]

    result, again, price = asyncio.run(_with_pool(scenario))
    assert result["status"] == "completed"
    assert result["bonus_spent"] == int(price * loyalty.MAX_REDEEM_SHARE)  # не больше половины стоимости
    assert result["accrued"] == 500  # 5% от 10 000 ₽ по Золотой карте
    assert again == 0  # повторно за тот же визит не начисляется


def test_client_filters_whitelist_and_operators():
    params: dict = {}
    sql = loyalty.condition(0, {"field": "purchases", "op": "gt", "value": "3"}, params)
    assert "c.purchases >" in sql and params["f0"] == 3.0
    assert "ILIKE" in loyalty.condition(1, {"field": "name", "op": "contains", "value": "анн"}, params)
    assert "IS NULL" in loyalty.condition(2, {"field": "birth_date", "op": "empty"}, params)
    assert loyalty.condition(3, {"field": "age", "op": "gt", "value": ""}, params) == "TRUE"
    with pytest.raises(ValueError):
        loyalty.condition(4, {"field": "password; DROP TABLE guests", "op": "eq", "value": "x"}, params)


def test_filtered_audience_respects_ads_consent():
    async def scenario():
        rows = await automations.audience([{"field": "gender", "op": "eq", "value": "f"}])
        return rows

    rows = asyncio.run(_with_pool(scenario))
    assert rows and all(r["gender"] == "f" and r["ads_ok"] for r in rows)


def test_birthday_automation_runs_once_per_guest():
    async def scenario():
        guest = await db.query_one("SELECT id FROM guests WHERE phone IS NOT NULL ORDER BY id DESC LIMIT 1")
        soon = booking.now().date() + timedelta(days=3)
        await db.query("UPDATE guests SET birth_date = %s WHERE id = %s RETURNING id", (soon.replace(year=1990), guest["id"]))
        label = "Тест ДР " + uuid.uuid4().hex[:6]
        auto = await automations.save({"name": label, "trigger": "birthday_before", "days": 7, "action": "bonus",
                                       "bonus_amount": 111, "bonus_days": 5, "message": "", "filters": [], "active": True})
        try:
            first = await automations.run_automation(auto)
            second = await automations.run_automation(auto)
            gifts = await db.query_one(
                "SELECT count(*) AS n FROM bonus_tx WHERE guest_id = %s AND kind = 'gift' AND note = %s", (guest["id"], label)
            )
        finally:
            await db.query("DELETE FROM automations WHERE id = %s RETURNING id", (auto["id"],))
        return first, second, gifts["n"]

    first, second, gifts = asyncio.run(_with_pool(scenario))
    assert first >= 1 and second == 0 and gifts == 1


def test_employee_pin_login_and_roles():
    stored = staff.hash_pin("2468")
    assert staff.check_pin("2468", stored)
    assert not staff.check_pin("1357", stored)
    assert staff.ROLE_TABS["cleaning"] == ["checklists"]
    assert "master" not in staff.FULL_ACCESS

    async def scenario():
        login = "test" + uuid.uuid4().hex[:6]
        emp = await staff.save_employee({"name": "Тест", "position": "cleaning", "login": login, "pin": "8642", "active": True})
        try:
            return await staff.employee_login(login, "8642"), await staff.employee_login(login, "0000")
        finally:
            await db.query("DELETE FROM employees WHERE id = %s RETURNING id", (emp["id"],))

    ok, bad = asyncio.run(_with_pool(scenario))
    assert ok["role"] == "cleaning" and bad is None
