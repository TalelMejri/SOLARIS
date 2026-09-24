import { useCallback, useState } from "react";
import { useSelector, useDispatch } from "react-redux";
import {
  LoginUser as loginAction,
  LogoutUser as logoutAction,
} from "@/AuthStore/slice";
import type { AppDispatch, RootState } from "@/AuthStore/store";
import type { LoginCredentials, User } from "@/models/AuthModels";
import {
  login as loginRequest,
  logout as logoutRequest,
} from "@/services/auth/auth_service";

export const useAuth = () => {
  const dispatch: AppDispatch = useDispatch();
  const { user, isAuth } = useSelector((state: RootState) => state.auth);
  const [isLoading, setIsLoading] = useState(false);


  const login = useCallback(
    async (credentials: LoginCredentials): Promise<User> => {
      setIsLoading(true);
      try {
        const { user: u } = await loginRequest(credentials);
        dispatch(loginAction({ user: u }));  
        return u;
      } finally {
        setIsLoading(false);
      }
    },
    [dispatch],
  );

  const logout = useCallback(async (): Promise<void> => {
    try {
      await logoutRequest();
    } catch {
    }
    dispatch(logoutAction());
  }, [dispatch]);

  return {
    user,
    isAuth,
    isLoading,
    login,
    logout,
    LoginUser: (u: User) => dispatch(loginAction({ user: u })),
    LogoutUser: () => dispatch(logoutAction()),
  };
};