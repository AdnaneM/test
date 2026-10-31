"""Notifications Telegram : grille du jour avec boutons « Joué / Passé », et traitement des réponses."""

from __future__ import annotations

import html
import logging
import threading
import time
from datetime import date

import httpx

from edgebet.config import Settings
from edgebet.db import repo
from edgebet.db.session import session_scope
from edgebet.serialize import rec_to_dict

log = logging.getLogger(__name__)

RISK_STARS = {1: "★☆☆☆☆", 2: "★★☆☆☆", 3: "★★★☆☆", 4: "★★★★☆", 5: "★★★★★"}
LEAGUE_FLAGS = {"F1": "🇫🇷", "F2": "🇫🇷", "E0": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "E1": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "SP1": "🇪🇸", "SP2": "🇪🇸", "D1": "🇩🇪", "D2": "🇩🇪",
                "I1": "🇮🇹", "I2": "🇮🇹", "N1": "🇳🇱", "P1": "🇵🇹", "B1": "🇧🇪", "T1": "🇹🇷", "SC0": "🏴󠁧󠁢󠁳󠁣󠁴󠁿"}


class TelegramClient:
    def __init__(self, token: str, client: httpx.Client | None = None, timeout: float = 35.0):
        if not token:
            raise ValueError("Jeton Telegram manquant (EDGEBET_TELEGRAM_BOT_TOKEN)")
        self.base = f"https://api.telegram.org/bot{token}"
        self.client = client or httpx.Client(timeout=timeout)

    def _post(self, method: str, **payload) -> dict:
        resp = self.client.post(f"{self.base}/{method}", json={k: v for k, v in payload.items() if v is not None})
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram {method} : {data.get('description', resp.text)}")
        return data["result"]

    def get_me(self) -> dict:
        return self._post("getMe")

    def send_message(self, chat_id: str, text: str, reply_markup: dict | None = None) -> dict:
        return self._post("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                          disable_web_page_preview=True, reply_markup=reply_markup)

    def edit_message_reply_markup(self, chat_id: str, message_id: int, reply_markup: dict | None) -> dict:
        return self._post("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id, reply_markup=reply_markup or {"inline_keyboard": []})

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> dict:
        return self._post("answerCallbackQuery", callback_query_id=callback_query_id, text=text)

    def get_updates(self, offset: int | None = None, timeout: int = 25) -> list[dict]:
        return self._post("getUpdates", offset=offset, timeout=timeout, allowed_updates=["callback_query", "message"])


def _pct(v: float | None) -> str:
    return "–" if v is None else f"{v * 100:+.1f} %".replace(".", ",")


def _eur(v: float | None) -> str:
    return "–" if v is None else f"{v:.2f} €".replace(".", ",")


def _kickoff(iso: str | None) -> str:
    if not iso:
        return ""
    d = iso[:16].replace("T", " ")
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(iso)
        jours = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
        return f"{jours[dt.weekday()]} {dt:%d/%m} {dt:%H:%M}"
    except ValueError:
        return d


def format_header(recs: list[dict], day: date, bankroll: float) -> str:
    total = sum(r["stake"] for r in recs)
    avg_edge = sum(r["edge"] for r in recs) / len(recs) if recs else 0.0
    return (
        f"🎯 <b>Grille EdgeBet du {day:%d/%m/%Y}</b>\n"
        f"{len(recs)} pari(s) · mise totale {_eur(total)} · edge moyen {_pct(avg_edge)}\n"
        f"Bankroll : {_eur(bankroll)}"
    )


def format_bet(r: dict) -> str:
    flag = LEAGUE_FLAGS.get(r["league"], "⚽")
    home, away = html.escape(r["home"]), html.escape(r["away"])
    pick = html.escape(r["pick_label"])
    book = html.escape(r.get("bookmaker_label") or r["bookmaker"])
    fair = r.get("fair_odds_sharp")
    fair_txt = f" (juste {fair:.2f})".replace(".", ",") if fair else ""
    lines = [
        f"{flag} <b>{home} – {away}</b> · {html.escape(r.get('league_name') or r['league'])} · {_kickoff(r.get('kickoff'))}",
        f"➡️ <b>{pick}</b> @ <b>{r['odds']:.2f}</b> {book}{fair_txt}".replace(f"{r['odds']:.2f}", f"{r['odds']:.2f}".replace(".", ",")),
        f"Edge {_pct(r['edge'])} · Proba {r['p_model'] * 100:.0f} % · Mise <b>{_eur(r['stake'])}</b> · Risque {RISK_STARS.get(r['risk'], '')}",
    ]
    if r.get("edge_vs_sharp") is not None:
        lines.append(f"vs Pinnacle : {_pct(r['edge_vs_sharp'])}")
    return "\n".join(lines)


def keyboard_for(r: dict) -> dict:
    rid = r["id"]
    decision = r.get("decision", "pending")
    if decision == "pending":
        row1 = [
            {"text": "✅ Joué", "callback_data": f"mark:{rid}:played"},
            {"text": "⏭ Passé", "callback_data": f"mark:{rid}:skipped"},
        ]
    else:
        label = "✅ Joué" if decision == "played" else "⏭ Passé"
        row1 = [{"text": f"{label} · ↩️ Annuler", "callback_data": f"mark:{rid}:pending"}]
    rows = [row1]
    if r.get("bookmaker_url"):
        rows.append([{"text": f"🔗 Ouvrir {r.get('bookmaker_label') or r['bookmaker']}", "url": r["bookmaker_url"]}])
    return {"inline_keyboard": rows}


def send_grid(client: TelegramClient, chat_id: str, recs: list[dict], day: date, bankroll: float) -> list[int]:
    """Envoie l'en-tête puis un message par pari (avec boutons). Retourne les message_id des paris."""
    if not chat_id:
        raise ValueError("Chat Telegram manquant (EDGEBET_TELEGRAM_CHAT_ID)")
    client.send_message(chat_id, format_header(recs, day, bankroll))
    ids: list[int] = []
    for r in recs:
        msg = client.send_message(chat_id, format_bet(r), reply_markup=keyboard_for(r))
        ids.append(int(msg.get("message_id", 0)))
    return ids


def send_text(s: Settings, text: str) -> None:
    TelegramClient(s.telegram_bot_token).send_message(s.telegram_chat_id, text)


def parse_callback(data: str) -> tuple[int, str] | None:
    parts = (data or "").split(":")
    if len(parts) != 3 or parts[0] != "mark":
        return None
    try:
        return int(parts[1]), parts[2]
    except ValueError:
        return None


def handle_update(update: dict, s: Settings, client: TelegramClient) -> bool:
    cq = update.get("callback_query")
    if not cq:
        return False
    parsed = parse_callback(cq.get("data", ""))
    if parsed is None:
        client.answer_callback_query(cq["id"], "Action inconnue")
        return False
    rec_id, decision = parsed
    chat_id = str(cq["message"]["chat"]["id"]) if cq.get("message") else s.telegram_chat_id
    if s.telegram_chat_id and chat_id != str(s.telegram_chat_id):
        client.answer_callback_query(cq["id"], "Non autorisé")
        return False
    with session_scope(s.db_url) as session:
        rec = repo.get_recommendation(session, rec_id)
        if rec is None:
            client.answer_callback_query(cq["id"], "Pari introuvable")
            return False
        repo.mark_recommendation(session, rec, decision)
        payload = rec_to_dict(rec, s)
    client.answer_callback_query(cq["id"], {"played": "Noté : joué ✅", "skipped": "Noté : passé ⏭", "pending": "Remis en attente"}[decision])
    if cq.get("message"):
        try:
            client.edit_message_reply_markup(chat_id, cq["message"]["message_id"], keyboard_for(payload))
        except RuntimeError as exc:  # message trop ancien, etc.
            log.debug("editMessageReplyMarkup : %s", exc)
    return True


def poll_forever(s: Settings, stop: threading.Event | None = None, client: TelegramClient | None = None) -> None:
    """Long polling getUpdates : aucune URL publique ni webhook nécessaire."""
    client = client or TelegramClient(s.telegram_bot_token)
    offset: int | None = None
    log.info("Telegram : écoute des réponses démarrée")
    while stop is None or not stop.is_set():
        try:
            for upd in client.get_updates(offset=offset, timeout=25):
                offset = int(upd["update_id"]) + 1
                try:
                    handle_update(upd, s, client)
                except Exception as exc:
                    log.warning("Telegram : traitement impossible (%s)", exc)
        except Exception as exc:
            log.warning("Telegram : getUpdates en échec (%s), nouvel essai dans 10 s", exc)
            time.sleep(10)
