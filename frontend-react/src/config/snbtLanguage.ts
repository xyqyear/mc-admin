// SNBT differs from JSON in ways that drive these regexes: numeric type suffixes
// (b/s/L/f/d), typed array prefixes ([B;], [I;], [L;]), and unquoted keys.
import type * as monaco from 'monaco-editor';

export const snbtLanguageDefinition: monaco.languages.IMonarchLanguage = {
  defaultToken: 'invalid',
  tokenPostfix: '.snbt',

  keywords: [],
  typeKeywords: [],

  numberSuffixes: /[bBsSLlfFdD]/,

  arrayTypes: /[BIL]/,

  symbols: /[=><!~?:&|+\-*/^%]+/,

  escapes: /\\(?:[abfnrtv\\"']|x[0-9A-Fa-f]{1,4}|u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8})/,

  tokenizer: {
    root: [
      { include: '@whitespace' },

      [/[{}]/, '@brackets'],

      [/\[([BIL]);/, ['@brackets', 'type.identifier']],
      [/[[\]]/, '@brackets'],

      [/:/, 'delimiter'],

      [/,/, 'delimiter'],

      [/[a-zA-Z_][\w]*(?=\s*:)/, 'key'],

      [/-?\d+(\.\d+)?[eE][+-]?\d+[fFdD]?/, 'number.float'],
      [/-?\d+\.\d+[fFdD]?/, 'number.float'],
      [/-?\d+[bBsSLl]/, 'number.integer'],
      [/-?\d+/, 'number'],

      [/"([^"\\]|\\.)*$/, 'string.invalid'],
      [/'([^'\\]|\\.)*$/, 'string.invalid'],
      [/"/, 'string', '@string_double'],
      [/'/, 'string', '@string_single'],

      [/\b(true|false)\b/, 'constant.language.boolean'],
    ],

    whitespace: [
      [/[ \t\r\n]+/, ''],
      [/\/\*/, 'comment', '@comment'],
      [/\/\/.*$/, 'comment'],
    ],

    comment: [
      [/[^/*]+/, 'comment'],
      [/\*\//, 'comment', '@pop'],
      [/[/*]/, 'comment'],
    ],

    string_double: [
      [/[^\\"]+/, 'string'],
      [/@escapes/, 'string.escape'],
      [/\\./, 'string.escape.invalid'],
      [/"/, 'string', '@pop'],
    ],

    string_single: [
      [/[^\\']+/, 'string'],
      [/@escapes/, 'string.escape'],
      [/\\./, 'string.escape.invalid'],
      [/'/, 'string', '@pop'],
    ],
  },
};

export const snbtLanguageConfiguration: monaco.languages.LanguageConfiguration = {
  comments: {
    lineComment: '//',
    blockComment: ['/*', '*/'],
  },
  brackets: [
    ['{', '}'],
    ['[', ']'],
  ],
  autoClosingPairs: [
    { open: '{', close: '}' },
    { open: '[', close: ']' },
    { open: '"', close: '"' },
    { open: "'", close: "'" },
  ],
  surroundingPairs: [
    { open: '{', close: '}' },
    { open: '[', close: ']' },
    { open: '"', close: '"' },
    { open: "'", close: "'" },
  ],
  folding: {
    markers: {
      start: new RegExp('^\\s*//\\s*#?region\\b'),
      end: new RegExp('^\\s*//\\s*#?endregion\\b'),
    },
  },
};
