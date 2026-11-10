import {afterEach, expect, it} from 'vitest';
import Cookies from 'js-cookie';

afterEach(() => Cookies.remove('synthetic-cookie'));

it('does not widen cookie attributes through an untrusted prototype key', () => {
  const attributes = JSON.parse('{"__proto__":{"sameSite":"None","domain":"attacker.invalid"}}');
  const serialized = Cookies.set('synthetic-cookie', 'synthetic-value', attributes);
  expect(serialized).toBe('synthetic-cookie=synthetic-value; path=/');
  expect(Cookies.get('synthetic-cookie')).toBe('synthetic-value');
});
