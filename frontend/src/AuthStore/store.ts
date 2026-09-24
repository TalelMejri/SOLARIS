import { configureStore } from "@reduxjs/toolkit";
import authReducer from "@/AuthStore/slice";

export const store = configureStore({
    reducer: {
        auth: authReducer,
    },
});

store.subscribe(() => {
    if (typeof window === 'undefined') return;
    try {
        const { auth } = store.getState();
        localStorage.setItem('auth', JSON.stringify(auth));
    } catch (e) {
        console.error('Failed to save auth state', e);
    }
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;