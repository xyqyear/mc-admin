// https://nuxt.com/docs/api/configuration/nuxt-config

export default defineNuxtConfig({
  compatibilityDate: "2024-11-01",
  devtools: { enabled: true },
  modules: [
    "@nuxtjs/tailwindcss",
    "@element-plus/nuxt",
    "@pinia/nuxt",
    "@nuxt/icon",
    "@vueuse/nuxt",
  ],
  ssr: false,
  // does this do anything?
  // css: ['element-plus/dist/index.css'],
  elementPlus: {
    // all the icons should has this as prefix. e.g. ElIconLoading
    icon: "ElIcon",
    importStyle: "scss",
  },
  vite: {
    css: {
      // prevent sass from complaining about old api version
      preprocessorOptions: {
        scss: {
          api: "modern-compiler",
        },
      },
    },
  },
  icon: {
    componentName: "NuxtIcon",
  },
  runtimeConfig: {
    public: {
      apiBaseUrl: process.env.API_BASE_URL,
    },
  },
});
