import { ChatScreen } from '@/features/chat/ChatScreen';
import { ScreenFade } from '@/components/ScreenFade';

export default function ChatPage() {
  return (
    <ScreenFade>
      <ChatScreen />
    </ScreenFade>
  );
}
