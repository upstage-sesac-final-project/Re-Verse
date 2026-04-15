import { describe, it, expect } from 'vitest';
import { annotateCommand } from './commandAnnotator.js';
import { EVENT_CODES } from './constants.js';

describe('commandAnnotator', () => {
  it('should annotate Show Text command', () => {
    const cmd = {
      code: EVENT_CODES.SHOW_TEXT,
      parameters: [0, 0]
    };
    const annotated = annotateCommand(cmd);
    expect(annotated._description).toContain('Show Text');
  });

  it('should annotate Text command', () => {
    const cmd = {
      code: EVENT_CODES.TEXT_DATA,
      parameters: ['Hello World']
    };
    const annotated = annotateCommand(cmd);
    expect(annotated._description).toContain('Hello World');
  });

  it('should annotate Show Choices command', () => {
    const cmd = {
      code: EVENT_CODES.SHOW_CHOICES,
      parameters: [['Yes', 'No'], 0, 0, 0]
    };
    const annotated = annotateCommand(cmd);
    expect(annotated._description).toContain('Show Choices');
  });

  it('should annotate Control Switches command', () => {
    const cmd = {
      code: EVENT_CODES.CONTROL_SWITCHES,
      parameters: [1, 5, 0] // Switch 1-5 = ON
    };
    const annotated = annotateCommand(cmd);
    expect(annotated._description).toContain('Control Switches');
    expect(annotated._description).toContain('ON');
  });

  it('should annotate Loop command', () => {
    const cmd = {
      code: EVENT_CODES.LOOP,
      parameters: []
    };
    const annotated = annotateCommand(cmd);
    expect(annotated._description).toBe('Loop');
  });

  it('should annotate Break Loop command', () => {
    const cmd = {
      code: EVENT_CODES.BREAK_LOOP,
      parameters: []
    };
    const annotated = annotateCommand(cmd);
    expect(annotated._description).toBe('Break Loop');
  });

  it('should annotate Conditional Branch command', () => {
    const cmd = {
      code: EVENT_CODES.CONDITIONAL_BRANCH,
      parameters: [0, 1, 0, 2] // Code=0, A=1, Op=0, B=2
    };
    const annotated = annotateCommand(cmd);
    expect(annotated._description).toContain('Conditional Branch');
  });

  it('should preserve original command properties', () => {
    const cmd = {
      code: EVENT_CODES.SHOW_TEXT,
      parameters: [0, 0],
      indent: 0
    };
    const annotated = annotateCommand(cmd);
    expect(annotated.code).toBe(cmd.code);
    expect(annotated.parameters).toEqual(cmd.parameters);
    expect(annotated.indent).toBe(cmd.indent);
  });

  it('should return undefined description for unknown command', () => {
    const cmd = {
      code: 99999,
      parameters: []
    };
    const annotated = annotateCommand(cmd);
    expect(annotated._description).toBeUndefined();
  });
});
