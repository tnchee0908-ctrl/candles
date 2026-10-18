#!/bin/sh
# Проверка силы тестов: каждый мутант (реалистичная ошибка) вносится в копию кода, набор тестов
# должен упасть. «ВЫЖИЛ» — значит, тесты эту ошибку не ловят.
# Запуск: docker compose run --rm tests sh scripts/mutants.sh [часть названия мутанта]
FILTER="$1"
run() {
  name="$1"; file="$2"; from="$3"; to="$4"
  case "$name" in *"$FILTER"*) ;; *) return ;; esac
  rm -rf /tmp/m && cp -r /app /tmp/m && cd /tmp/m
  python - "$file" "$from" "$to" <<'PY'
import sys
from pathlib import Path
p = Path(sys.argv[1]); s = p.read_text(encoding="utf-8")
assert sys.argv[2] in s, "pattern not found: " + sys.argv[2]
p.write_text(s.replace(sys.argv[2], sys.argv[3], 1), encoding="utf-8")
PY
  if pytest -q -x -p no:cacheprovider > /tmp/out.txt 2>&1; then echo "ВЫЖИЛ  $name"; else echo "убит   $name ($(grep -m1 FAILED /tmp/out.txt | cut -c1-90))"; fi
}
run "нет блокировки задания при планировании" app/services/orders.py "order = await load_order(session, order_id, lock=True)
    _require_status(order, {OrderStatus.DRAFT, OrderStatus.PLANNED}" "order = await load_order(session, order_id, lock=False)
    _require_status(order, {OrderStatus.DRAFT, OrderStatus.PLANNED}"
run "нет перечитывания партий" app/services/orders.py "        .with_for_update()
        .execution_options(populate_existing=True)
    )
    existing" "        .with_for_update()
    )
    existing"
run "дорезерв перезаписывает" app/services/orders.py "existing[batch.id].qty += take" "existing[batch.id].qty = take"
run "перерасход без блокировки" app/services/orders.py "            .order_by(Batch.received_date, Batch.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        for batch in batches:
            free = batch.remaining_qty - batch.reserved_qty
            if free <= 0:
                continue
            take = min(free, to_consume)" "            .order_by(Batch.received_date, Batch.id)
        )
        for batch in batches:
            free = batch.remaining_qty - batch.reserved_qty
            if free <= 0:
                continue
            take = min(free, to_consume)"
run "Принята -> Брак" app/services/batches.py "    BatchStatus.ON_CHECK: {BatchStatus.ACCEPTED, BatchStatus.REJECTED}," "    BatchStatus.ON_CHECK: {BatchStatus.ACCEPTED, BatchStatus.REJECTED},
    BatchStatus.ACCEPTED: {BatchStatus.REJECTED},"
run "другое округление денег" app/services/common.py "return value.quantize(MONEY_STEP, rounding=ROUND_HALF_UP)" "return value.quantize(MONEY_STEP)"
run "имя файла без маскирования" app/assistant/uploads.py 'return f"upload_{file_id}{Path(filename).suffix.lower()}"' 'return filename'
run "дедупликация фактов между пользователями" app/assistant/memory.py "select(UserFact).where(UserFact.user_id == actor.user_id, func.lower(UserFact.text) == text.lower())" "select(UserFact).where(func.lower(UserFact.text) == text.lower())"
run "ошибка в потоке без запасной" app/assistant/llm/router.py "                if started:" "                if True:"
run "снят лимит шагов" app/assistant/chat.py "for _step in range(self.settings.llm_max_tool_steps):" "for _step in range(1000):"
run "выдача в цех не списывает" app/services/orders.py "        batch.remaining_qty -= reservation.qty
        session.add(_consumption(order, batch, reservation.qty))" "        session.add(_consumption(order, batch, reservation.qty))"
run "цитата для памяти не проверяется" app/assistant/tools.py "    memory.check_quote(args.source_quote, ctx.user_message)" "    pass"
run "имена подставляются в ссылки" app/assistant/pii.py "            out.append(url.group(0))" "            out.append(self._unmask_plain(url.group(0)))"
run "404 модели не переключает" app/assistant/llm/openai_provider.py "    if status == 404:
        return True" "    if status == 404:
        return False"
