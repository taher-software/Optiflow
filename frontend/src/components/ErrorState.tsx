/** Bandeau d'erreur d'une page de données : un serveur injoignable ou une
 * erreur backend ne doit jamais être confondu avec « aucune donnée », ni
 * laisser des chiffres faux (zéros, écarts calculés sur du vide) à l'écran.
 * Le conteneur décide quoi masquer ; ce composant ne fait qu'afficher. */
export function ErrorState({
  title,
  detail,
  retryLabel,
  onRetry,
}: {
  title: string;
  detail: string;
  retryLabel: string;
  onRetry: () => void;
}) {
  return (
    <section
      role="alert"
      className="mt-10 rounded-2xl border border-[#fecaca] bg-[#fef2f2] p-5"
    >
      <h2 className="text-[14px] font-semibold text-[#b91c1c]">{title}</h2>
      <p className="mt-1 text-[13px] text-[#7f1d1d]">{detail}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 rounded-lg border border-[#fca5a5] bg-white px-3 py-1.5 text-[13px] font-medium text-[#b91c1c] hover:bg-[#fff1f2]"
      >
        {retryLabel}
      </button>
    </section>
  );
}

export default ErrorState;
