import React from 'react';
import {Tag} from '../../types';

interface TagGroupProps {
  tags: Tag[];
}

export const TagGroup: React.FC<TagGroupProps> = ({tags}) => {
  return (
    <div className="flex flex-wrap gap-2 max-sm:flex-wrap">
      {tags.map((tag, index) => (
        <span
          key={index}
          className={`px-3 py-2 text-sm rounded-full ${
            tag.variant === 'blue' ? 'bg-blue-100 text-blue-800' : 'bg-red-100 text-red-800'
          }`}
        >
          {tag.text}
        </span>
      ))}
    </div>
  );
};
