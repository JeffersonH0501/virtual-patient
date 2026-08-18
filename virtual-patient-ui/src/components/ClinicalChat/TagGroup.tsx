import React from 'react';
import {Tag} from '../../types';

interface TagGroupProps {
  tags: Tag[];
  tone?: 'default' | 'warning';
}

export const TagGroup: React.FC<TagGroupProps> = ({tags, tone = 'default'}) => {
  return (
    <div className="flex flex-wrap gap-2 max-sm:flex-wrap">
      {tags.map((tag, index) => (
        <span
          key={index}
          className={`rounded-full px-3 py-2 text-sm ${
            tone === 'warning'
              ? 'bg-yellow-100 text-yellow-900'
              : tag.variant === 'blue'
                ? 'bg-blue-100 text-blue-800'
                : 'bg-red-100 text-red-800'
          }`}
        >
          {tag.text}
        </span>
      ))}
    </div>
  );
};
