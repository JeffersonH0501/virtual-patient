import React from 'react';
import {Badge} from '../common/Badge';
import {Tag} from '../../types';

interface TagGroupProps {
  tags: Tag[];
  tone?: 'default' | 'warning';
}

export const TagGroup: React.FC<TagGroupProps> = ({tags, tone = 'default'}) => {
  return (
    <div className="flex flex-wrap gap-layout max-sm:flex-wrap">
      {tags.map((tag, index) => (
        <Badge key={index} tone={tone === 'warning' ? 'warning' : tag.variant === 'blue' ? 'info' : 'danger'}>
          {tag.text}
        </Badge>
      ))}
    </div>
  );
};
