import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {createInstance} from 'i18next';
import {I18nextProvider} from 'react-i18next';
import es from '../../../i18n/locales/es.json';
import en from '../../../i18n/locales/en.json';
import {HelpModal} from './index';

afterEach(cleanup);

it.each(['es', 'en'] as const)(
  'shows complete information with native numbered and bulleted lists in %s',
  async (language) => {
    const i18n = createInstance();
    await i18n.init({lng: language, resources: {es: {translation: es}, en: {translation: en}}});
    const close = vi.fn();
    render(
      <I18nextProvider i18n={i18n}>
        <HelpModal isOpen onClose={close} />
      </I18nextProvider>,
    );
    const text = language === 'es' ? es.help : en.help;
    const dialog = screen.getByRole('dialog', {name: text.title});
    expect(dialog.classList.contains('modal-panel--large')).toBe(true);
    expect(within(dialog).getByRole('heading', {level: 2}).classList.contains('dialog-title')).toBe(
      true,
    );
    expect(within(dialog).getAllByRole('heading', {level: 3})).toHaveLength(4);
    expect(dialog.querySelector('details')).toBeNull();
    for (const section of [text.purpose, text.objective]) {
      expect(within(dialog).getByText(section.description)).toBeTruthy();
    }
    expect(within(dialog).getByText(text.clinicalCases.description)).toBeTruthy();
    expect(
      within(dialog)
        .getByText(text.additionalInfo.description)
        .classList.contains('dialog-annotation'),
    ).toBe(true);
    const lists = within(dialog).getAllByRole('list');
    expect(lists.map((list) => list.tagName)).toEqual(['OL', 'UL']);
    expect(within(dialog).getAllByRole('listitem')).toHaveLength(8);
    expect(within(dialog).getByText(text.clinicalCases.feature2)).toBeTruthy();
    expect(
      within(dialog)
        .getAllByRole('listitem')
        .some((item) => item.classList.contains('flex')),
    ).toBe(false);
    fireEvent.click(
      within(dialog).getByRole('button', {
        name: language === 'es' ? es.common.close : en.common.close,
      }),
    );
    expect(close).toHaveBeenCalledOnce();
  },
);
