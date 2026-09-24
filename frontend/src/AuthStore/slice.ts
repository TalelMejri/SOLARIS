// AuthStore/slice.ts
import type { User } from '@/models/AuthModels'
import { createSlice } from '@reduxjs/toolkit'
import type { PayloadAction } from '@reduxjs/toolkit'

interface AuthState {
  user: User | null
  isAuth: boolean
}

const STORAGE_KEY = 'auth'

const loadState = (): AuthState => {
  if (typeof window === 'undefined') return { user: null, isAuth: false }
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) return JSON.parse(saved) as AuthState
  } catch (e) {
    console.error('Failed to load auth state', e)
  }
  return { user: null, isAuth: false }
}

const persistState = (state: AuthState) => {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch (e) {
    console.error('Failed to persist auth state', e)
  }
}

const initialState: AuthState = loadState()

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    LoginUser: (state, action: PayloadAction<{ user: User }>) => {
      state.isAuth = true
      state.user = action.payload.user
      persistState({ user: state.user, isAuth: true })
    },
    LogoutUser: (state) => {
      state.isAuth = false
      state.user = null
      if (typeof window !== 'undefined') {
        localStorage.removeItem(STORAGE_KEY)
      }
    },
  },
})

export const { LoginUser, LogoutUser } = authSlice.actions
export default authSlice.reducer