import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';

export type MeProfile = {
  height_cm: number | null;
  weight_kg: number | null;
  age: number | null;
  sex: 'male' | 'female' | null;
  activity_level: string | null;
  calorie_goal_override: number | null;
};

export function useMeProfile() {
  return useQuery<MeProfile | null>({
    queryKey: ['me-profile'],
    queryFn: async () => {
      const { data } = await api.GET('/me/profile');
      if (!data) return null;
      return {
        height_cm: data.height_cm ?? null,
        weight_kg: data.weight_kg ?? null,
        age: data.age ?? null,
        sex: (data.sex ?? null) as MeProfile['sex'],
        activity_level: (data.activity_level ?? null) as string | null,
        calorie_goal_override: data.calorie_goal_override ?? null,
      };
    },
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}
