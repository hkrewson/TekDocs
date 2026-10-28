import { mergeConfig } from 'vite'
import base from './vite.config'

export default mergeConfig(base, {
  server: { proxy: { '/api': 'http://migrate:8081', '/_allauth': 'http://migrate:8081' } },
})
