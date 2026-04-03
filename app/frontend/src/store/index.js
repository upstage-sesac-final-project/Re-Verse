import { configureStore } from '@reduxjs/toolkit'
import userReducer from './userSlice'
import gameReducer from './gameSlice'

export const store = configureStore({
  reducer: {
    user: userReducer,
    game: gameReducer,
  },
})
