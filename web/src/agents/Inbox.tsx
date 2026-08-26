// Where jobs report. Flagged items say what was flagged and quote it, because "an agent read
// something odd" is only useful if you can see the something.
import { useAgents } from "../store/agents";
import Button from "../ui/Button";

export default function Inbox() {
  const inbox = useAgents((s) => s.inbox);
  const markRead = useAgents((s) => s.markRead);

  if (inbox.length === 0) {
    return <p className="px-3 py-4 text-sm text-ink-faint">Nothing yet. Jobs report here.</p>;
  }

  return (
    <div className="flex flex-col gap-2 px-3 py-2">
      {inbox.map((item) => (
        <article
          key={item.id}
          className={`glass rounded-xl p-3 ${item.read_at ? "opacity-60" : ""}`}
        >
          <div className="flex items-baseline gap-2">
            <h3 className="min-w-0 flex-1 truncate text-sm text-ink">{item.title}</h3>
            {item.flags.map((flag) => (
              <span
                key={flag}
                className="rounded-full bg-amber-300/15 px-2 py-0.5 text-[11px] text-amber-200"
                title="Something in what this run read was trying to give instructions."
              >
                {flag}
              </span>
            ))}
          </div>
          <p className="mt-2 whitespace-pre-wrap text-sm text-ink-muted">{item.body}</p>
          <div className="mt-2 flex justify-end">
            <Button onClick={() => void markRead(item.id, !item.read_at)}>
              {item.read_at ? "mark unread" : "mark read"}
            </Button>
          </div>
        </article>
      ))}
    </div>
  );
}
