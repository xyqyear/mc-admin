/**
 * SNBT (Stringified NBT) Language Definition for Monaco Editor
 *
 * SNBT is Minecraft's text representation of NBT (Named Binary Tag) data.
 * It's similar to JSON but with different syntax rules:
 * - Supports byte (b), short (s), long (L), float (f), double (d) suffixes
 * - Uses square brackets for lists: [I;1,2,3] for int arrays
 * - Curly braces for compounds: {key:value}
 * - Keys can be unquoted if they contain only alphanumeric and underscore
 */

import type * as monaco from 'monaco-editor';

export const snbtLanguageDefinition: monaco.languages.IMonarchLanguage = {
  defaultToken: 'invalid',
  tokenPostfix: '.snbt',

  // Keywords and type suffixes
  keywords: [],
  typeKeywords: [],

  // Number type suffixes
  numberSuffixes: /[bBsSLlfFdD]/,

  // Array type prefixes
  arrayTypes: /[BIL]/,

  // Symbols
  symbols: /[=><!~?:&|+\-*/^%]+/,

  // Escape sequences
  escapes: /\\(?:[abfnrtv\\"']|x[0-9A-Fa-f]{1,4}|u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8})/,

  tokenizer: {
    root: [
      // Whitespace
      { include: '@whitespace' },

      // Compound (object) braces
      [/[{}]/, '@brackets'],

      // Array brackets with optional type prefix
      [/\[([BIL]);/, ['@brackets', 'type.identifier']],
      [/[[\]]/, '@brackets'],

      // Key-value separator
      [/:/, 'delimiter'],

      // List separator
      [/,/, 'delimiter'],

      // Unquoted keys (alphanumeric and underscore)
      [/[a-zA-Z_][\w]*(?=\s*:)/, 'key'],

      // Numbers with type suffixes
      [/-?\d+(\.\d+)?[eE][+-]?\d+[fFdD]?/, 'number.float'],
      [/-?\d+\.\d+[fFdD]?/, 'number.float'],
      [/-?\d+[bBsSLl]/, 'number.integer'],
      [/-?\d+/, 'number'],

      // Strings (double and single quoted)
      [/"([^"\\]|\\.)*$/, 'string.invalid'], // non-terminated string
      [/'([^'\\]|\\.)*$/, 'string.invalid'], // non-terminated string
      [/"/, 'string', '@string_double'],
      [/'/, 'string', '@string_single'],

      // Boolean-like values (common in NBT)
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

/**
 * SNBT Language Configuration
 * Defines bracket matching, auto-closing pairs, and other editor behaviors
 */
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
