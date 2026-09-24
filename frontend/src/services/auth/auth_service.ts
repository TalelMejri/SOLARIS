import type { AuthResponse, LoginCredentials, RegisterData, User } from '@/models/AuthModels';
import api from '../apiClients';

export const refresh_token = async (): Promise<void> => {
    try {
        const response = await api.post('/auth/refresh');
        return response.data;
    } catch (error) {
        console.error('Token refresh failed:', error);
        throw error;
    }
};

export const login = async (credentials: LoginCredentials): Promise<AuthResponse> => {
    const response = await api.post('/auth/login', credentials);
    return response.data;
};

export const register = async (userData: RegisterData): Promise<AuthResponse> => {
    const response = await api.post('/auth/register', userData,);
    return response.data;
};

export const logout = async (): Promise<void> => {
    await api.post('/auth/logout');
};

export const getCurrentUser = async (): Promise<User> => {
    const response = await api.get('/me');
    return response.data.user;
};

