export function Avatar({ name, size = 26 }: { name: string; size?: number }) {
  const initial = name.trim().slice(0, 1).toUpperCase() || "?";
  return (
    <span className="avatar" aria-hidden="true" style={{ width: size, height: size, fontSize: Math.round(size * 0.46) }}>
      {initial}
    </span>
  );
}
