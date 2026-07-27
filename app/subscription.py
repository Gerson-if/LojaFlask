"""
subscription.py — Sistema de assinatura/pagamento do LojaFácil.

Regras de negócio:
  - Ao criar conta: trial de TRIAL_DAYS dias é iniciado automaticamente
  - Acesso liberado se: trial ainda ativo OU subscription_active = True
  - Superadmin pode:
      • Renovar assinatura (definir paid_until para N meses à frente)
      • Suspender manualmente (zera subscription_active e paid_until)
      • Reativar (recalcula paid_until)
  - Ao expirar (paid_until < hoje E subscription_active True):
      subscription_active é marcado False automaticamente no first-request
  - Lojista sem acesso → dashboard redireciona para /assinatura-expirada
  - Loja pública sem acesso → retorna 503 (loja temporariamente indisponível)
"""

from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, abort, redirect, render_template, url_for
from flask_login import current_user, login_required

subscription_bp = Blueprint("subscription", __name__)

# ── Configurações ──────────────────────────────────────────────────────────────
TRIAL_DAYS = 14
PLAN_PRICE_MONTHLY = 20.0


# ── Helpers de status ──────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    """Garante que um datetime é timezone-aware (UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# Alias público — outros módulos (ex.: dashboard.py) usam essa função para
# normalizar datetimes vindos do banco antes de comparar com `now(timezone.utc)`,
# evitando o erro "can't compare offset-naive and offset-aware datetimes".
as_aware = _aware


def store_access_status(store) -> dict:
    """
    Retorna um dict descrevendo o estado de acesso da loja:
      {
        "has_access": bool,
        "mode": "trial" | "paid" | "expired" | "none",
        "days_left": int | None,
        "paid_until": datetime | None,
        "trial_ends_at": datetime | None,
      }
    """
    if store is None:
        return {"has_access": False, "mode": "none", "days_left": None,
                "paid_until": None, "trial_ends_at": None}

    now = _now_utc()

    # Assinatura paga ativa
    if store.subscription_active:
        paid_until = _aware(store.paid_until)
        if paid_until is None or paid_until >= now:
            days = (paid_until - now).days if paid_until else None
            return {"has_access": True, "mode": "paid", "days_left": days,
                    "paid_until": paid_until, "trial_ends_at": _aware(store.trial_ends_at)}
        # Assinatura marcada como ativa mas vencida — corrige automaticamente
        _expire_store(store)
        return {"has_access": False, "mode": "expired", "days_left": 0,
                "paid_until": paid_until, "trial_ends_at": _aware(store.trial_ends_at)}

    # Trial
    trial_end = _aware(store.trial_ends_at)
    if trial_end is not None and trial_end >= now:
        days = max(0, (trial_end - now).days)
        return {"has_access": True, "mode": "trial", "days_left": days,
                "paid_until": None, "trial_ends_at": trial_end}

    return {"has_access": False, "mode": "expired", "days_left": 0,
            "paid_until": _aware(store.paid_until), "trial_ends_at": trial_end}


def store_has_access(store) -> bool:
    """Atalho booleano — True se a loja tem acesso."""
    return store_access_status(store)["has_access"]


def _expire_store(store):
    """Marca subscription_active=False no banco (side-effect intencional)."""
    try:
        from . import db
        store.subscription_active = False
        db.session.commit()
    except Exception:
        pass


# ── Decorators ─────────────────────────────────────────────────────────────────

def require_active_subscription(f):
    """
    Para views do painel do lojista.
    Aplique depois de @login_required e @lojista_required.
    Redireciona para /assinatura-expirada se não tiver acesso.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        store = getattr(current_user, "store", None)
        if not store_has_access(store):
            return redirect(url_for("subscription.blocked"))
        return f(*args, **kwargs)
    return decorated


def require_active_storefront(store):
    """
    Para a vitrine pública.
    Aborta com 503 se a loja não tiver acesso ativo. A própria `store` é
    anexada ao erro (via `description`) para que o handler de erro 503 possa
    montar uma página de "loja indisponível" usando a identidade visual
    daquela loja (cores, logo), sem nunca expor o motivo real (inadimplência)
    ao cliente final.
    """
    if not store_has_access(store):
        abort(503, description=store)


# ── Rotas ──────────────────────────────────────────────────────────────────────

@subscription_bp.route("/assinatura-expirada")
@login_required
def blocked():
    store = getattr(current_user, "store", None)
    if store and store_has_access(store):
        return redirect(url_for("dashboard.index"))
    status = store_access_status(store)
    return render_template(
        "subscription/blocked.html",
        price=PLAN_PRICE_MONTHLY,
        status=status,
    )


# ── Context processor ──────────────────────────────────────────────────────────

def subscription_context_processor():
    """
    Injeta no contexto de todos os templates:
      - subscription_status: dict completo
      - trial_days_left: int (compat. retroativa)
      - store_active: bool (compat. retroativa)
    """
    if current_user.is_authenticated and not current_user.is_superadmin():
        store = getattr(current_user, "store", None)
        status = store_access_status(store)
        return {
            "subscription_status": status,
            "trial_days_left": status["days_left"] or 0,
            "store_active": status["has_access"],
        }
    return {
        "subscription_status": {"has_access": True, "mode": "paid", "days_left": None,
                                 "paid_until": None, "trial_ends_at": None},
        "trial_days_left": 0,
        "store_active": True,
    }
