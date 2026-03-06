import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listUsers,
  getUser,
  createUser,
  updateUser,
  deleteUser,
  resetPassword,
  type User,
  type UsersListResponse,
  type CreateUserInput,
  type UpdateUserInput,
} from "../api/users";

export function useUsersQuery() {
  return useQuery<UsersListResponse, Error>({
    queryKey: ["users"],
    queryFn: listUsers,
  });
}

export function useUserQuery(id: number | null) {
  return useQuery<User, Error>({
    queryKey: ["user", id],
    queryFn: () => getUser(id!),
    enabled: id !== null && id > 0,
  });
}

export function useCreateUserMutation() {
  const queryClient = useQueryClient();
  return useMutation<User, Error, CreateUserInput>({
    mutationFn: createUser,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}

export function useUpdateUserMutation() {
  const queryClient = useQueryClient();
  return useMutation<User, Error, { id: number; input: UpdateUserInput }>({
    mutationFn: ({ id, input }) => updateUser(id, input),
    onSuccess: (_, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      void queryClient.invalidateQueries({ queryKey: ["user", variables.id] });
    },
  });
}

export function useDeleteUserMutation() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, number>({
    mutationFn: deleteUser,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}

export function useResetPasswordMutation() {
  return useMutation<void, Error, { id: number; newPassword: string }>({
    mutationFn: ({ id, newPassword }) => resetPassword(id, newPassword),
  });
}
