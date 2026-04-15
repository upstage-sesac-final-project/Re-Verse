import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    include: ['**/*.test.js', '**/*.test.ts'],
    exclude: ['node_modules', 'test_project'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'test_project/',
        '**/*.test.js',
        '**/*.test.ts',
        'automation/',
      ],
    },
  },
});
