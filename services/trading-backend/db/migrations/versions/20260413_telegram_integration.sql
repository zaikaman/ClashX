ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS telegram_chat_id bigint,
ADD COLUMN IF NOT EXISTS telegram_chat_type character varying,
ADD COLUMN IF NOT EXISTS telegram_username character varying,
ADD COLUMN IF NOT EXISTS telegram_first_name character varying,
ADD COLUMN IF NOT EXISTS telegram_connected_at timestamp with time zone,
ADD COLUMN IF NOT EXISTS telegram_last_interaction_at timestamp with time zone,
ADD COLUMN IF NOT EXISTS telegram_link_code character varying,
ADD COLUMN IF NOT EXISTS telegram_link_code_expires_at timestamp with time zone,
ADD COLUMN IF NOT EXISTS telegram_notifications_enabled boolean NOT NULL DEFAULT true,
ADD COLUMN IF NOT EXISTS telegram_notification_prefs jsonb NOT NULL DEFAULT '{"critical_alerts": true, "execution_failures": true, "copy_activity": true}'::jsonb;

CREATE UNIQUE INDEX IF NOT EXISTS users_telegram_chat_id_idx
ON public.users (telegram_chat_id)
WHERE telegram_chat_id IS NOT NULL;
