/** Shows exactly what the AI agents did, step by step. */
export default function TraceLedger({ steps }: { steps: string[] }) {
  return (
    <ol className="ledger" aria-label="What the agents did">
      {steps.map((s, i) => {
        const cut = s.indexOf(": ");
        const agent = cut > 0 ? s.slice(0, cut) : "";
        const text = cut > 0 ? s.slice(cut + 2) : s;
        const bad = /denied|failed|could not/i.test(s);
        return (
          <li key={i} className={bad ? "bad" : "ok"}>
            {agent && <strong>{agent}</strong>} {text}
          </li>
        );
      })}
    </ol>
  );
}
