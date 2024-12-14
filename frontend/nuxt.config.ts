// https://nuxt.com/docs/api/configuration/nuxt-config

export default defineNuxtConfig({
  compatibilityDate: '2024-11-01',
  devtools: { enabled: true },
  modules: ['@nuxtjs/tailwindcss', '@element-plus/nuxt', '@pinia/nuxt', '@nuxt/icon'],
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
          api: 'modern-compiler',
        }
      }
    }
  },
  icon: {
    componentName: 'NuxtIcon',
  }
})
