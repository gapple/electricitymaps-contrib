import { defineConfig } from 'cypress';

export default defineConfig({
  fileServerFolder: 'dist',
  fixturesFolder: '../mockserver/public',
  projectId: '9z8tgk',
  video: false,
  watchForFileChanges: true,
  e2e: {
    baseUrl: 'http://127.0.0.1:5173/',
    specPattern: 'cypress/e2e/**/*.ts',
    pageLoadTimeout: 10_000, // Increase to 2 minutes
    defaultCommandTimeout: 10_000,
  },
  component: {
    devServer: {
      framework: 'react',
      bundler: 'vite',
    },
    setupNodeEvents(on, _config) {
      on('before:browser:launch', (browser, launchOptions) => {
        if (browser.family === 'chromium' && browser.name !== 'electron') {
          launchOptions.preferences.default.intl = {
            accept_languages: 'en-US,en',
            selected_languages: 'en-US,en',
          };

          return launchOptions;
        }
      });
    },
  },
});
