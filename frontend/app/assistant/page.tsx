import { getTranslations } from "next-intl/server";

import { Topbar } from "@/components/layout/Topbar";
import { ChatView } from "@/components/assistant/ChatView";

export default async function AssistantPage() {
  const tNav = await getTranslations("Nav");
  const t = await getTranslations("Assistant");

  return (
    <>
      <Topbar title={tNav("assistant")} description={t("topbarDescription")} />
      <main className="flex-1 overflow-hidden">
        <ChatView />
      </main>
    </>
  );
}
