import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type LoginPreference = 'password' | 'code'

interface LoginPreferenceStore {
  loginPreference: LoginPreference
  setLoginPreference: (preference: LoginPreference) => void
}

export const useLoginPreferenceStore = create<LoginPreferenceStore>()(
  persist(
    (set) => ({
      loginPreference: 'code',
      setLoginPreference: (preference: LoginPreference) =>
        set({ loginPreference: preference }),
    }),
    {
      name: 'loginPreference',
    }
  )
)
