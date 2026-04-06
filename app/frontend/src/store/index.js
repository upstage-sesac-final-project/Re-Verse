import { configureStore } from '@reduxjs/toolkit'
import userReducer from './userSlice'
import gameReducer from './gameSlice'
import generationReducer from './generationSlice'

export const store = configureStore({
  reducer: {
    user: userReducer,
    game: gameReducer,
    generation: generationReducer,
  },
})
