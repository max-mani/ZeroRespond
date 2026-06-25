// src/components/ui/Skeleton.tsx
export function SkeletonRow() {
    return (
      <tr className="animate-pulse">
        {Array.from({ length: 7 }).map((_, i) => (
          <td key={i} className="px-4 py-3">
            <div className="h-3 bg-surface-600 rounded w-3/4" />
          </td>
        ))}
      </tr>
    );
  }
  
  export function SkeletonCard() {
    return (
      <div className="bg-surface-800 rounded-xl border border-surface-700 p-6 animate-pulse">
        <div className="h-4 bg-surface-600 rounded w-1/3 mb-3" />
        <div className="h-8 bg-surface-600 rounded w-1/4" />
      </div>
    );
  }