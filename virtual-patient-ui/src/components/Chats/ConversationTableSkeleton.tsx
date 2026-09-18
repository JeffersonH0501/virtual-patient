import {FC} from 'react';
import {Skeleton} from '../common';

const SKELETON_ROW_COUNT = 5;

/**
 * Skeleton-loading placeholder for the conversation history table body.
 * Rendered inside the existing table while interviews are being fetched.
 */
export const ConversationTableSkeleton: FC = () => (
  <>
    {Array.from({length: SKELETON_ROW_COUNT}).map((_, index) => (
      <tr key={index} className="conversation-table-columns border-t border-slate-100" aria-hidden="true">
        <td className="px-6 py-4 max-sm:px-3"><Skeleton className="h-4 w-24" /></td>
        <td className="px-6 py-4 max-sm:px-3"><Skeleton className="h-4 w-40" /></td>
        <td className="px-6 py-4 max-sm:px-3"><Skeleton className="h-4 w-16" /></td>
        <td className="px-6 py-4 max-sm:px-3"><Skeleton className="h-6 w-20 rounded-full" /></td>
        <td className="px-6 py-4 max-sm:px-3"><Skeleton className="h-4 w-10" /></td>
        <td className="px-6 py-4 max-sm:px-3"><Skeleton className="h-8 w-8 rounded-lg" /></td>
      </tr>
    ))}
  </>
);
