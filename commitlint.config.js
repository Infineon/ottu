module.exports = {
  parserPreset: {
    parserOpts: {
      headerPattern: /^([a-zA-Z0-9_\-\/]+):\s(.*)$/,
      headerCorrespondence: ['scope', 'subject'],
    },
  },

  plugins: [
    {
      rules: {
        'scope-subject-format': ({ header }) => {
          const scopeSubjectRegex = /^[A-Za-z0-9_./\-]+:\s[A-Z].*\.$/;

          return [
            scopeSubjectRegex.test(header),
            `Commit message must match style:\n` +
              `  Expected: "path/to/file: Capitalized sentence description."\n` +
              `  Received: "${header}"`,
          ];
        },

        'signed-off-by': ({ raw }) => {
          const signoffRegex = /(?:^|\n)Signed-off-by:\s.+<.+>\s*$/m;

          return [
            signoffRegex.test(raw),
            'Commit message must include a Signed-off-by trailer.',
          ];
        },
      },
    },
  ],

  rules: {
    'scope-subject-format': [2, 'always'],
    'signed-off-by': [2, 'always'],
    'header-max-length': [2, 'always', 78],
  },
};