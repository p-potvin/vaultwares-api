// /lib/validation/vaultcore.ts
import { z } from 'zod';

export const createOrderSchema = z.object({
  userId: z.string().uuid(),
  modelId: z.string().min(1),
  mode: z.enum(['server', 'local']),
  payload: z.unknown(), // narrow after decrypt
});

export const identitySchema = z.object({
  email: z.string().email(),
  password: z.string().min(12),
});

export type CreateOrderInput = z.infer<typeof createOrderSchema>;
