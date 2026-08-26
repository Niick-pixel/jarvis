// Every tool call that ever happened, as it is stored: paths, hosts, outcomes, and hashes.
//
// There are no arguments and no content here, and that is not an omission in the UI - the writer
// never had them (BRIEF.md 7). Grants live here too, since revoking one is an audit-shaped act.
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AuditEntry, ToolGrant } from "../api/types";
import Button from "../ui/Button";

const OUTCOME_STYLE: Record<string, string> = {
  ran: "text-emerald-200",
  refused: "text-rose-200",
  failed: "text-rose-200",
  awaiting_approval: "text-amber-200",
};

export default function AuditLog() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [grants, setGrants] = useState<ToolGrant[]>([]);

  const load = () => {
    void api.auditLog().then(setEntries).catch(() => undefined);
    void api.grants().then(setGrants).catch(() => undefined);
  };
  useEffect(load, []);

  return (
    <div className="flex flex-col gap-3 px-3 py-2 text-sm">
      <section>
        <h3 className="mb-1 text-[11px] uppercase tracking-wide text-ink-faint">
          Standing permissions
        </h3>
        {grants.length === 0 && (
          <p className="text-xs text-ink-faint">
            None. Every side effect is asked for, one at a time.
          </p>
        )}
        {grants.map((grant) => (
          <div key={`${grant.tool}:${grant.scope}`} className="flex items-center gap-2 py-1">
            <span className="text-ink">{grant.tool}</span>
            <code className="min-w-0 flex-1 truncate text-xs text-ink-faint" title={grant.scope}>
              {grant.scope}
            </code>
            <Button
              onClick={() =>
                void api.revokeGrant(grant.tool, grant.scope).then(load).catch(() => undefined)
              }
            >
              Revoke
            </Button>
          </div>
        ))}
      </section>

      <section>
        <div className="mb-1 flex items-center gap-2">
          <h3 className="text-[11px] uppercase tracking-wide text-ink-faint">Audit log</h3>
          <Button onClick={load}>Refresh</Button>
        </div>
        {entries.length === 0 && <p className="text-xs text-ink-faint">Nothing has run yet.</p>}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-ink-faint">
              <tr>
                <th className="py-1 pr-2 font-normal">when</th>
                <th className="py-1 pr-2 font-normal">who</th>
                <th className="py-1 pr-2 font-normal">tool</th>
                <th className="py-1 pr-2 font-normal">outcome</th>
                <th className="py-1 pr-2 font-normal">target</th>
                <th className="py-1 pr-2 font-normal">args</th>
                <th className="py-1 font-normal">result</th>
              </tr>
            </thead>
            <tbody className="text-ink-muted">
              {entries.map((entry) => (
                <tr key={entry.id} className="border-t border-white/5 align-top">
                  <td className="py-1 pr-2 whitespace-nowrap">
                    {new Date(entry.at).toLocaleTimeString()}
                  </td>
                  <td className="py-1 pr-2">{entry.actor}</td>
                  <td className="py-1 pr-2 text-ink">{entry.tool}</td>
                  <td className={`py-1 pr-2 ${OUTCOME_STYLE[entry.outcome] ?? ""}`}>
                    {entry.outcome.replace("_", " ")}
                  </td>
                  <td className="max-w-[16rem] break-all py-1 pr-2 font-mono">{entry.target}</td>
                  <td className="py-1 pr-2 font-mono">{entry.args_hash}</td>
                  <td className="py-1 font-mono">
                    {entry.result_hash ? `${entry.result_hash} · ${entry.bytes}B` : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
