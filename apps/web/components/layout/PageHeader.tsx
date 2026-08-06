export function PageHeader({ title, description }: { title: string; description: string }) {
  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight text-black dark:text-zinc-50">
        {title}
      </h1>
      <p className="mt-1 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">{description}</p>
    </div>
  );
}
