import React, { useState } from 'react';
import { initialsOf } from '../utils/avatar';

/**
 * A person's photo next to their name, or their initials when there is none (hidden, not uploaded, failed
 * to load). Decorative: the name is always written beside it.
 */
const Avatar = ({ name = '', url = null, size = 'sm', className = '' }) => {
  const [failed, setFailed] = useState(false);
  return (
    <span className={`avatar avatar-${size} ${className}`} aria-hidden="true">
      {url && !failed
        ? <img src={url} alt="" loading="lazy" decoding="async" onError={() => setFailed(true)} />
        : <span className="avatar-initials">{initialsOf(name)}</span>}
    </span>
  );
};

export default Avatar;
