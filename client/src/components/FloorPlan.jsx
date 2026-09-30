import React, { useId } from 'react';
import { FLOOR_PLANS, KIND_STYLE, VIEW, boundsOf, isPickable } from '../data/floorPlans';
import { plural } from '../utils/plural';

// One floor of корпус Б drawn from data: rooms coloured by kind, the selected one filled and pinned.
//   facts     { [room id]: room from /api/v1/rooms } — places and computers under the numbers
//   selected  room id to highlight; matches — Set of ids that fit a filter (null: no filter)
//   onSelect  makes numbered rooms buttons; compact — numbers only, cropped around the selected room

const kindOf = (room, facts) => facts?.[room.id]?.type || room.kind || 'office';
const toneOf = (kind) => (KIND_STYLE[kind] || KIND_STYLE.office).tone;

// Under the number: computers when there are any, else places
export const roomSubtitle = (fact) => {
  if (!fact) return '';
  const parts = [];
  if (fact.pcs) parts.push(`${fact.pcs} ПК`);
  if (fact.laptops) parts.push(`${fact.laptops} ноут.`);
  if (parts.length) return parts.join(' · ');
  return fact.seats ? `${fact.seats} ${plural(fact.seats, ['место', 'места', 'мест'])}` : '';
};

export const roomTitle = (room) => (/^\d{3}$/.test(room.id) ? `Б-${room.id}` : room.label || room.id);

const cropAround = (room) => {
  const b = boundsOf(room);
  const width = 980;
  const cx = (b.x0 + b.x1) / 2;
  const x = Math.min(Math.max(cx - width / 2, VIEW.x), VIEW.x + VIEW.width - width);
  return `${x} ${VIEW.y} ${width} ${VIEW.height}`;
};

const Shape = ({ room, className }) => {
  if (room.points) return <polygon className={className} points={room.points.map((p) => p.join(',')).join(' ')} />;
  return <rect className={className} x={room.x0} y={room.y0} width={room.x1 - room.x0} height={room.y1 - room.y0} />;
};

const Pin = ({ x, y }) => (
  <g className="plan-pin" transform={`translate(${x} ${y}) scale(1.35)`} aria-hidden="true">
    <g className="plan-pin-body">
      <path d="M0 0 C-6 -14 -22 -26 -22 -42 A22 22 0 1 1 22 -42 C22 -26 6 -14 0 0 Z" />
      <circle cx="0" cy="-42" r="8.5" />
    </g>
  </g>
);

const FloorPlan = ({ floor, facts = null, selected = null, matches = null, onSelect = null, compact = false, className = '' }) => {
  const uid = useId().replace(/:/g, '');
  const plan = FLOOR_PLANS[floor];
  if (!plan) return null;
  const chosen = plan.rooms.find((r) => r.id === selected) || null;
  const viewBox = compact && chosen ? cropAround(chosen) : `${VIEW.x} ${VIEW.y} ${VIEW.width} ${VIEW.height}`;

  const pick = (id) => (e) => {
    if (e.type === 'keydown' && e.key !== 'Enter' && e.key !== ' ') return;
    e.preventDefault();
    onSelect(id);
  };

  const renderRoom = (room) => {
    const b = boundsOf(room);
    const w = b.x1 - b.x0;
    const h = b.y1 - b.y0;
    const cx = room.labelAt?.[0] ?? (b.x0 + b.x1) / 2;
    const cy = room.labelAt?.[1] ?? (b.y0 + b.y1) / 2;
    const fact = facts?.[room.id];
    const kind = kindOf(room, facts);
    const numbered = /^\d{3}$/.test(room.id);
    const text = room.label || (numbered ? room.id : '');
    const note = room.note && !compact ? room.note : '';
    const sub = !compact && !note ? roomSubtitle(fact) : '';
    const interactive = !!onSelect && isPickable(room);
    const state = [
      'plan-room',
      `tone-${toneOf(kind)}`,
      interactive ? 'is-pickable' : '',
      room.id === selected ? 'is-selected' : '',
      matches && interactive ? (matches.has(room.id) ? 'is-match' : 'is-dim') : '',
    ].filter(Boolean).join(' ');
    const big = text.length > 4;
    const size = big ? Math.min(30, (w - 24) / (text.length * 0.56)) : compact ? 44 : 40;
    // A line under the number shrinks to fit a narrow room, or is left out
    const fit = (line) => Math.min(24, (w - 28) / (line.length * 0.55));
    const lines = [note, sub].filter((line) => line && fit(line) >= 15 && h >= 110);
    const top = cy - (lines.length ? 13 : 0);

    const body = (
      <>
        <Shape room={room} className="plan-room-shape" />
        {matches?.has(room.id) && room.id !== selected && !room.points && (
          <rect className="plan-room-ring" x={b.x0 + 7} y={b.y0 + 7} width={w - 14} height={h - 14} rx="4" />
        )}
        {text && (
          <text className={`plan-room-number ${big ? 'is-word' : ''}`} x={cx} y={top} fontSize={size} dominantBaseline="central" textAnchor="middle">
            {text}
          </text>
        )}
        {lines.map((line, i) => (
          <text key={line} className="plan-room-sub" x={cx} y={top + size * 0.72 + 8 + i * 28} fontSize={fit(line)} dominantBaseline="central" textAnchor="middle">
            {line}
          </text>
        ))}
      </>
    );

    if (!interactive) return <g key={room.id} className={state} aria-hidden="true">{body}</g>;
    const about = [roomTitle(room), note || KIND_STYLE[kind]?.label, roomSubtitle(fact), fact?.os].filter(Boolean).join(', ');
    return (
      <g
        key={room.id}
        className={state}
        role="button"
        tabIndex={0}
        aria-pressed={room.id === selected}
        aria-label={about}
        onClick={pick(room.id)}
        onKeyDown={pick(room.id)}
      >
        {body}
      </g>
    );
  };

  const tall = (s) => s.y1 - s.y0 > s.x1 - s.x0;
  const pinAt = chosen && (() => {
    const b = boundsOf(chosen);
    return { x: chosen.labelAt?.[0] ?? (b.x0 + b.x1) / 2, y: (chosen.labelAt?.[1] ?? (b.y0 + b.y1) / 2) - (compact ? 30 : 34) };
  })();

  return (
    <svg
      className={`plan ${compact ? 'plan-compact' : ''} ${className}`}
      viewBox={viewBox}
      role="group"
      aria-label={`Схема ${floor} этажа корпуса Б${chosen ? `, выделена ${roomTitle(chosen)}` : ''}`}
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <pattern id={`${uid}-steps-h`} width="12" height="12" patternUnits="userSpaceOnUse">
          <path d="M0 6H12" className="plan-step" />
        </pattern>
        <pattern id={`${uid}-steps-v`} width="12" height="12" patternUnits="userSpaceOnUse">
          <path d="M6 0V12" className="plan-step" />
        </pattern>
      </defs>

      {plan.shell.map((s, i) => (
        <rect key={`shell-${i}`} className="plan-shell" x={s.x0} y={s.y0} width={s.x1 - s.x0} height={s.y1 - s.y0} rx="3" />
      ))}
      {plan.corridors.map((c, i) => (
        <rect key={`corridor-${i}`} className="plan-corridor" x={c.x0} y={c.y0} width={c.x1 - c.x0} height={c.y1 - c.y0} />
      ))}

      {plan.entrance && (
        <g className="plan-entrance" aria-hidden="true">
          <rect className="plan-porch" x={plan.entrance.porch.x0} y={plan.entrance.porch.y0}
            width={plan.entrance.porch.x1 - plan.entrance.porch.x0} height={plan.entrance.porch.y1 - plan.entrance.porch.y0} />
          {plan.entrance.steps.map((s, i) => (
            <rect key={i} className="plan-stairs" fill={`url(#${uid}-steps-h)`} x={s.x0} y={s.y0} width={s.x1 - s.x0} height={s.y1 - s.y0} />
          ))}
          <path className="plan-entrance-arrow" d="M954 612 V560 M936 578 L954 558 L972 578" />
          <text className="plan-entrance-label" x="954" y="530" textAnchor="middle" dominantBaseline="central" fontSize="26">Вход</text>
        </g>
      )}

      <g aria-hidden="true">
        {plan.stairs.map((s, i) => (
          <rect key={`stairs-${i}`} className="plan-stairs" fill={`url(#${uid}-steps-${tall(s) ? 'h' : 'v'})`}
            x={s.x0} y={s.y0} width={s.x1 - s.x0} height={s.y1 - s.y0} />
        ))}
        {plan.wc.map((s, i) => (
          <g key={`wc-${i}`}>
            <rect className="plan-wc" x={s.x0} y={s.y0} width={s.x1 - s.x0} height={s.y1 - s.y0} />
            <text className="plan-wc-label" x={(s.x0 + s.x1) / 2} y={(s.y0 + s.y1) / 2} textAnchor="middle" dominantBaseline="central" fontSize="22">WC</text>
          </g>
        ))}
      </g>

      {plan.rooms.map(renderRoom)}

      {!compact && plan.halls?.map((hall) => (
        <text key={hall.label} className="plan-hall-label" x={hall.x} y={hall.y} textAnchor="middle" dominantBaseline="central" fontSize="28" aria-hidden="true">
          {hall.label}
        </text>
      ))}

      {pinAt && <Pin key={selected} x={pinAt.x} y={pinAt.y - (compact ? 14 : 12)} />}
    </svg>
  );
};

export default FloorPlan;
