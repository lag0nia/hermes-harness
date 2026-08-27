from hermes_harness.delivery import (
    DeliveryEvent,
    DeliveryEventType,
    DeliveryRouter,
)


def test_start_milestone_and_terminal_return_to_origin():
    router = DeliveryRouter()
    events = [
        DeliveryEvent("job-1", "telegram:42", DeliveryEventType.START, "Investigación iniciada"),
        DeliveryEvent("job-1", "telegram:42", DeliveryEventType.MILESTONE, "Fuente verificada"),
        DeliveryEvent("job-1", "telegram:42", DeliveryEventType.TERMINAL, "Listo", terminal=True),
    ]
    outbound = router.route(events)
    assert [m.target for m in outbound] == ["telegram:42"] * 3
    assert all("job-1" not in m.text for m in outbound)


def test_telegram_extra_only_for_blocked_and_critical():
    router = DeliveryRouter(telegram_extra_target="telegram:99")
    blocked = DeliveryEvent(
        "j", "desktop:1", DeliveryEventType.BLOCKED, "Confirma compra", critical=False
    )
    critical = DeliveryEvent(
        "k", "desktop:1", DeliveryEventType.TERMINAL, "Fallo crítico", critical=True, terminal=True
    )
    normal = DeliveryEvent("n", "desktop:1", DeliveryEventType.TERMINAL, "Hecho", terminal=True)
    assert [m.target for m in router.route([blocked, critical, normal])].count("telegram:99") == 2


def test_deduplicates_callbacks_and_alternates_roles():
    router = DeliveryRouter()
    event = DeliveryEvent("j", "telegram:1", DeliveryEventType.START, "Comenzando", event_id="e1")
    msgs = router.route(
        [
            event,
            event,
            DeliveryEvent("j", "telegram:1", DeliveryEventType.BLOCKED, "Necesito confirmación"),
        ]
    )
    assert len(msgs) == 2
    assert [m.role for m in msgs] == ["assistant", "user"]


def test_ids_are_revealed_only_for_ambiguity_or_debug():
    router = DeliveryRouter()
    normal = router.route(
        [DeliveryEvent("abcdef123", "desktop:1", DeliveryEventType.START, "Inicio")]
    )[0]
    ambiguous = router.route(
        [
            DeliveryEvent(
                "abcdef123", "desktop:1", DeliveryEventType.STATUS, "¿Cuál?", reveal_id=True
            )
        ]
    )[0]
    assert "abcdef123" not in normal.text
    assert "abcdef1" in ambiguous.text


def test_disconnected_origin_is_buffered_and_can_be_queried_from_other_surface():
    router = DeliveryRouter()
    router.set_connected("telegram:7", False)
    router.route(
        [DeliveryEvent("j", "telegram:7", DeliveryEventType.TERMINAL, "Resultado", terminal=True)]
    )
    later = router.status("j", "desktop:2")
    assert later.target == "desktop:2"
    assert "Resultado" in later.text
