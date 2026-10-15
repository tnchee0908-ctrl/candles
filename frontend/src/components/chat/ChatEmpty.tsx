import { ChartLine, ClipboardList, MessageSquare, RussianRuble, TriangleAlert, type LucideIcon } from 'lucide-react';

const EXAMPLES: { icon: LucideIcon; text: string }[] = [
  { icon: TriangleAlert, text: 'Чего не хватит на задания этой недели?' },
  { icon: ClipboardList, text: 'Запланируй 200 свечей «Лаванда» на пятницу' },
  { icon: ChartLine, text: 'Построй график расхода воска по неделям за квартал' },
  { icon: RussianRuble, text: 'Как изменится себестоимость «Лаванды», если соевый воск подорожает на 15%?' },
];

/** Пустой чат: короткий заголовок, одна строка пояснения, 4 примера вопросов. */
export function ChatEmpty({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="flex flex-1 items-center justify-center px-8 py-7">
      <div className="-mt-16 w-full max-w-[640px]">
        <div className="mb-3 flex size-9 items-center justify-center rounded-lg bg-muted text-fg-muted">
          <MessageSquare className="size-[18px]" aria-hidden />
        </div>
        <h1 className="text-lg font-semibold">Ассистент мастерской</h1>
        <p className="mt-1 text-fg-muted">
          Отвечает по данным учёта, считает в Code Interpreter и готовит задания. Данные меняются только после вашего «Подтвердить».
        </p>
        <div className="mt-5 grid grid-cols-[repeat(auto-fit,minmax(min(100%,280px),1fr))] gap-2">
          {EXAMPLES.map(({ icon: Icon, text }) => (
            <button
              key={text}
              type="button"
              onClick={() => onPick(text)}
              className="flex items-start gap-2.5 rounded-lg border border-border bg-surface px-3.5 py-3 text-left transition-colors hover:border-border-strong hover:bg-subtle focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-accent/25"
            >
              <Icon className="mt-0.5 size-4 shrink-0 text-fg-subtle" aria-hidden />
              {text}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
