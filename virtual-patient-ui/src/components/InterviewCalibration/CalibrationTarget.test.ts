import {readFileSync} from 'node:fs';
import {parse} from 'postcss';
import {expect, it} from 'vitest';

it('keeps the gaze target centered throughout its entrance animation', () => {
  const stylesheet = parse(readFileSync('src/styles/design-system.css', 'utf8'));
  const animations: string[] = [];
  stylesheet.walkAtRules('keyframes', (rule) => {
    if (rule.params !== 'calibration-target-in') return;
    animations.push(rule.params);
    rule.walkDecls((declaration) => {
      // Tailwind centers the target with translate; an animated translation would move it twice.
      expect(['transform', 'translate', 'left', 'top']).not.toContain(declaration.prop);
    });
  });
  expect(animations).toEqual(['calibration-target-in']);
});
