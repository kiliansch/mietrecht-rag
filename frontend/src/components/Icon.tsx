// Material Symbols Outlined icon. `name` is the symbol ligature (e.g. "chat").
export function Icon({ name, className = "" }: { name: string; className?: string }) {
  return (
    <span className={`material-symbols-outlined ${className}`} aria-hidden>
      {name}
    </span>
  );
}
