import { Select } from '@base-ui/react/select';
import type { ReactNode } from 'react';
import type { Role } from '../data/types.ts';

export function SelectField({
  label, value, options, onChange, className = '',
}: {
  label: string;
  value: string | number;
  options: readonly { id: string | number; label: string; disabled?: boolean }[];
  onChange: (value: string) => void;
  className?: string;
}) {
  const items = options.map(({ id, label: text }) => ({ value: String(id), label: text }));
  return (
    <div className={`field ${className}`}>
      <Select.Root items={items} value={String(value)} modal={false}
        onValueChange={(next) => { if (next !== null) onChange(next); }}>
        <Select.Label className="field-label">{label}</Select.Label>
        <Select.Trigger className="dropdown-trigger">
          <Select.Value className="dropdown-value" />
          <span className="dropdown-icon" aria-hidden="true" />
        </Select.Trigger>
        <Select.Portal>
          <Select.Positioner className="dropdown-positioner" align="start" sideOffset={6}
            collisionPadding={12} alignItemWithTrigger={false}>
            <Select.Popup className="dropdown-popup">
              <Select.List>
                {options.map((option) => (
                  <Select.Item key={option.id} value={String(option.id)} disabled={option.disabled} className="dropdown-item">
                    <Select.ItemText>{option.label}</Select.ItemText>
                    <Select.ItemIndicator className="dropdown-check" aria-hidden="true">✓</Select.ItemIndicator>
                  </Select.Item>
                ))}
              </Select.List>
            </Select.Popup>
          </Select.Positioner>
        </Select.Portal>
      </Select.Root>
    </div>
  );
}

export function SectionTitle({ title, description, extra }: { title: string; description?: string; extra?: ReactNode }) {
  return (
    <div className="section-title">
      <div><h2>{title}</h2>{description && <p>{description}</p>}</div>
      {extra}
    </div>
  );
}

export function RoleMark({ role, variant = 'line' }: { role: Role; variant?: 'line' | 'bar' | 'dot' }) {
  return <span aria-hidden="true" className={`role-mark ${role} role-mark--${variant}`} />;
}

export function StatePanel({
  title, children, action, type = 'neutral',
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
  type?: 'neutral' | 'error' | 'locked';
}) {
  return (
    <section className={`panel state-panel state-panel--${type}`} role={type === 'error' ? 'alert' : 'status'}>
      <span className="state-symbol" aria-hidden="true">{type === 'error' ? '!' : type === 'locked' ? '⊘' : '∅'}</span>
      <div><h2>{title}</h2><p>{children}</p></div>
      {action}
    </section>
  );
}

export function Loading({ label }: { label: string }) {
  return (
    <div className="panel loading" role="status" aria-busy="true">
      <span>{label}</span>
      <div className="loading-lines" aria-hidden="true"><i /><i /><i /></div>
    </div>
  );
}
