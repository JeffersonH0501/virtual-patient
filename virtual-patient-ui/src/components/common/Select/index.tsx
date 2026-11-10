import {
  AriaAttributes,
  ChangeEventHandler,
  CSSProperties,
  FocusEventHandler,
  forwardRef,
  KeyboardEvent,
  KeyboardEventHandler,
  ReactNode,
  useEffect,
  useId,
  useRef,
  useState,
} from 'react';
import {useTranslation} from 'react-i18next';
import {createPortal} from 'react-dom';
import {ChevronDown} from 'lucide-react';
import {readDesignNumber} from '../../../utils/designTokens';
import {useAppMotion, usePresence} from '../Motion/hooks';

export type SelectOption = {
  value: string;
  label: ReactNode;
  searchText?: string;
  disabled?: boolean;
};
export type SelectProps = AriaAttributes & {
  id?: string;
  value: string;
  label?: string;
  placeholder?: string;
  options: SelectOption[];
  onValueChange?: (value: string) => void;
  onChange?: ChangeEventHandler<HTMLSelectElement>;
  onKeyDown?: KeyboardEventHandler<HTMLButtonElement>;
  onBlur?: FocusEventHandler<HTMLButtonElement>;
  name?: string;
  required?: boolean;
  disabled?: boolean;
  autoFocus?: boolean;
  autoComplete?: string;
  className?: string;
};
const TYPEAHEAD_RESET_MS = 700;

/** Shared select-only combobox with rich labels and native form participation. */
export const Select = forwardRef<HTMLButtonElement, SelectProps>(
  (
    {
      id: suppliedId,
      value,
      label,
      placeholder = '',
      options,
      onValueChange,
      onChange,
      onKeyDown,
      onBlur,
      name,
      required = false,
      disabled = false,
      autoFocus = false,
      autoComplete,
      className = '',
      ...aria
    },
    forwardedRef,
  ) => {
    const {t} = useTranslation();
    const nativeControl = useRef<HTMLSelectElement>(null);
    const [invalid, setInvalid] = useState(false);
    const [open, setOpen] = useState(false);
    const motion = useAppMotion();
    const presence = usePresence(open, '--app-motion-expand');
    const [placement, setPlacement] = useState<'top' | 'bottom'>('bottom');
    const [active, setActive] = useState(0);
    const [position, setPosition] = useState<CSSProperties>({});
    const trigger = useRef<HTMLButtonElement>(null);
    const popup = useRef<HTMLUListElement>(null);
    const optionElements = useRef<(HTMLLIElement | null)[]>([]);
    const search = useRef({text: '', time: 0});
    const generatedId = useId();
    const id = suppliedId ?? generatedId;
    const selected = options.find((option) => option.value === value);
    const enabled = options
      .map((option, index) => (option.disabled ? -1 : index))
      .filter((index) => index >= 0);
    const activeIndex = enabled.includes(active) ? active : (enabled[0] ?? -1);
    const accessibleLabel = aria['aria-label'] ?? label ?? placeholder;
    const optionText = (index: number) =>
      options[index].searchText ??
      (typeof options[index].label === 'string'
        ? (options[index].label as string)
        : options[index].value);
    const popupHost =
      trigger.current?.closest('[data-ui-select-portal-host]') ??
      (typeof document === 'undefined' ? null : document.body);

    const measure = () => {
      if (!trigger.current) return;
      const rect = trigger.current.getBoundingClientRect();
      const inset = readDesignNumber('--layout-inset');
      const limit = readDesignNumber('--select-menu-max-height');
      const below = Math.max(0, window.innerHeight - rect.bottom - inset);
      const above = Math.max(0, rect.top - inset);
      const flip = below < limit && above > below;
      setPlacement(flip ? 'top' : 'bottom');
      const width = Math.min(rect.width, Math.max(0, window.innerWidth - inset * 2));
      setPosition({
        '--select-menu-left':
          Math.max(inset, Math.min(rect.left, window.innerWidth - width - inset)) + 'px',
        '--select-menu-top': flip ? 'auto' : rect.bottom + 'px',
        '--select-menu-bottom': flip ? window.innerHeight - rect.top + 'px' : 'auto',
        '--select-menu-width': width + 'px',
        '--select-menu-max-height': Math.min(limit, flip ? above : below) + 'px',
      } as CSSProperties);
    };
    const show = () => {
      if (disabled) return;
      measure();
      search.current = {text: '', time: 0};
      const selectedIndex = options.findIndex(
        (option) => option.value === value && !option.disabled,
      );
      setActive(selectedIndex >= 0 ? selectedIndex : (enabled[0] ?? -1));
      setOpen(true);
    };
    const choose = (index: number) => {
      const option = options[index];
      if (!option || option.disabled || disabled) return;
      setOpen(false);
      trigger.current?.focus();
      search.current = {text: '', time: 0};
      if (nativeControl.current) {
        nativeControl.current.value = option.value;
        nativeControl.current.dispatchEvent(new Event('change', {bubbles: true}));
      }
    };
    useEffect(() => {
      if (!open) return;
      const outside = (event: Event) => {
        const target = event.target as Node | null;
        if (target && !trigger.current?.contains(target) && !popup.current?.contains(target)) {
          setOpen(false);
        }
      };
      window.addEventListener('resize', measure);
      window.addEventListener('scroll', measure, true);
      document.addEventListener('pointerdown', outside);
      document.addEventListener('focusin', outside);
      return () => {
        window.removeEventListener('resize', measure);
        window.removeEventListener('scroll', measure, true);
        document.removeEventListener('pointerdown', outside);
        document.removeEventListener('focusin', outside);
      };
    }, [open]);
    useEffect(() => {
      if (open) optionElements.current[activeIndex]?.scrollIntoView?.({block: 'nearest'});
    }, [open, activeIndex]);
    useEffect(() => {
      if (disabled) setOpen(false);
    }, [disabled]);

    const handleKey = (event: KeyboardEvent<HTMLButtonElement>) => {
      onKeyDown?.(event);
      if (event.defaultPrevented || disabled) return;
      if (event.key === 'Tab') {
        setOpen(false);
        return;
      }
      if (event.key === 'Escape' && open) {
        setOpen(false);
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'Enter', ' '].includes(event.key)) {
        event.preventDefault();
        if (!open) {
          show();
          return;
        }
        if (event.key === 'Enter' || event.key === ' ') choose(activeIndex);
        else if (event.key === 'Home') setActive(enabled[0] ?? -1);
        else if (event.key === 'End') setActive(enabled[enabled.length - 1] ?? -1);
        else if (enabled.length) {
          setActive(
            enabled[
              (enabled.indexOf(activeIndex) +
                (event.key === 'ArrowDown' ? 1 : enabled.length - 1)) %
                enabled.length
            ],
          );
        }
        return;
      }
      if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
        const now = Date.now();
        const text =
          (now - search.current.time < TYPEAHEAD_RESET_MS ? search.current.text : '') +
          event.key.toLocaleLowerCase();
        const query = [...text].every((character) => character === text[0]) ? text[0] : text;
        search.current = {text, time: now};
        const next = options
          .map((_, offset) => (activeIndex + offset + 1) % options.length)
          .find(
            (index) =>
              !options[index].disabled && optionText(index).toLocaleLowerCase().startsWith(query),
          );
        if (next != null) {
          if (!open) measure();
          setActive(next);
          setOpen(true);
        }
        event.preventDefault();
      }
    };
    return (
      <>
        <button
          ref={(element) => {
            trigger.current = element;
            if (typeof forwardedRef === 'function') forwardedRef(element);
            else if (forwardedRef) forwardedRef.current = element;
          }}
          {...aria}
          id={id}
          value={value}
          disabled={disabled}
          autoFocus={autoFocus}
          onBlur={onBlur}
          type="button"
          role="combobox"
          aria-label={accessibleLabel}
          aria-required={required || undefined}
          aria-invalid={aria['aria-invalid'] ?? (invalid || undefined)}
          aria-describedby={[id + '-value', aria['aria-describedby'], invalid && id + '-validation']
            .filter(Boolean)
            .join(' ')}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={open ? id + '-options' : undefined}
          aria-activedescendant={
            open && activeIndex >= 0 ? id + '-option-' + activeIndex : undefined
          }
          className={['ui-select ui-select-trigger', className].filter(Boolean).join(' ')}
          onClick={() => (open ? setOpen(false) : show())}
          onKeyDown={handleKey}
        >
          <span
            id={id + '-value'}
            className={
              selected?.disabled || (!value && !selected) ? 'ui-select-placeholder' : undefined
            }
          >
            {selected?.label ?? (value || placeholder)}
          </span>
          <ChevronDown />
        </button>
        <select
          ref={nativeControl}
          className="ui-select-native"
          tabIndex={-1}
          aria-hidden="true"
          name={name}
          value={value}
          required={required}
          disabled={disabled}
          autoComplete={autoComplete}
          onChange={(event) => {
            setInvalid(false);
            onValueChange?.(event.target.value);
            onChange?.(event);
          }}
          onInvalid={(event) => {
            event.preventDefault();
            setInvalid(true);
            trigger.current?.focus();
          }}
        >
          {!selected && <option value={value}>{value}</option>}
          {options.map((option, index) => (
            <option key={option.value} value={option.value} disabled={option.disabled}>
              {optionText(index)}
            </option>
          ))}
        </select>
        {invalid && (
          <span id={id + '-validation'} className="ui-field-error" role="alert">
            {t('common.selectRequired')}
          </span>
        )}
        {presence.present &&
          popupHost &&
          createPortal(
            <ul
              ref={popup}
              id={id + '-options'}
              role="listbox"
              aria-label={accessibleLabel}
              aria-hidden={!open || undefined}
              inert={!open}
              data-ui-motion={motion.enabled ? 'app' : undefined}
              data-placement={placement}
              data-motion-state={presence.state}
              onAnimationEnd={presence.onAnimationEnd}
              className="ui-select-listbox motion-popup"
              data-ui-select-owner={id}
              style={position}
            >
              {options.map((option, index) => (
                <li
                  key={option.value}
                  ref={(element) => {
                    optionElements.current[index] = element;
                  }}
                  id={id + '-option-' + index}
                  role="option"
                  aria-selected={option.value === value}
                  data-active={index === activeIndex || undefined}
                  aria-disabled={option.disabled || undefined}
                  className="ui-select-option"
                  onMouseDown={(event) => event.preventDefault()}
                  onMouseMove={() => {
                    if (!option.disabled) setActive(index);
                  }}
                  onClick={() => choose(index)}
                >
                  {option.label}
                </li>
              ))}
            </ul>,
            popupHost,
          )}
      </>
    );
  },
);
Select.displayName = 'Select';
