import {
  ButtonItem,
  PanelSection,
  PanelSectionRow,
  ToggleField,
  staticClasses,
} from "@decky/ui";
import { callable, definePlugin, toaster } from "@decky/api";
import { useState } from "react";
import { FaExchangeAlt } from "react-icons/fa";

type MirrorResult = {
  ok: boolean;
  error?: string;
  app_id?: number;
  source_path?: string;
  output_path?: string;
  swapped_tokens?: number;
};

type CreateMirrorArgs = {
  app_id: number;
  mirror_dpad: boolean;
  mirror_touchpads: boolean;
  mirror_sticks: boolean;
};

const createMirrorTemplateCall = callable<[args: CreateMirrorArgs], MirrorResult>(
  "create_mirror_template"
);

async function detectCurrentAppId(): Promise<number | undefined> {
  const win = window as any;
  const directCandidates = [
    win?.Router?.MainRunningApp?.appid,
    win?.SP_REACT?.Router?.MainRunningApp?.appid,
    win?.SteamUIStore?.MainRunningApp?.appid,
  ];

  for (const maybeId of directCandidates) {
    const numeric = Number(maybeId);
    if (Number.isFinite(numeric) && numeric > 0) {
      return numeric;
    }
  }

  const getRunningAppId = win?.SteamClient?.System?.GetRunningAppID;
  if (typeof getRunningAppId === "function") {
    try {
      const res = await getRunningAppId();
      const candidates = [res, res?.appid, res?.running_app_id, res?.result];
      for (const maybeId of candidates) {
        const numeric = Number(maybeId);
        if (Number.isFinite(numeric) && numeric > 0) {
          return numeric;
        }
      }
    } catch {
      return undefined;
    }
  }

  return undefined;
}

function Content() {
  const [mirrorDpad, setMirrorDpad] = useState<boolean>(true);
  const [mirrorTouchpads, setMirrorTouchpads] = useState<boolean>(true);
  const [mirrorSticks, setMirrorSticks] = useState<boolean>(false);
  const [isBusy, setIsBusy] = useState<boolean>(false);
  const [status, setStatus] = useState<string>("Ready");

  const createMirrorTemplate = async () => {
    if (isBusy) {
      return;
    }

    setIsBusy(true);
    setStatus("Creating mirror template...");
    try {
      const appId = await detectCurrentAppId();
      const result = await createMirrorTemplateCall({
        app_id: appId ?? 0,
        mirror_dpad: mirrorDpad,
        mirror_touchpads: mirrorTouchpads,
        mirror_sticks: mirrorSticks,
      });
      if (!result?.ok) {
        setStatus(result?.error ?? "Failed to create mirror template");
        return;
      }

      const appText = result.app_id ? `App ${result.app_id}` : "Current app";
      const swapsText = Number(result.swapped_tokens ?? 0);
      const nextStatus = `${appText}: saved (${swapsText} swaps)`;
      setStatus(nextStatus);
      toaster.toast({
        title: "Mirror template created",
        body: nextStatus,
      });
    } catch (error) {
      setStatus(`Error: ${String(error)}`);
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <PanelSection title="Mirror Template">
      <PanelSectionRow>
        <ToggleField
          label="Mirror D-pad + ABXY"
          checked={mirrorDpad}
          onChange={(value: boolean) => setMirrorDpad(value)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField
          label="Mirror Touchpads"
          checked={mirrorTouchpads}
          onChange={(value: boolean) => setMirrorTouchpads(value)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField
          label="Mirror Left/Right Sticks"
          checked={mirrorSticks}
          onChange={(value: boolean) => setMirrorSticks(value)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem onClick={createMirrorTemplate} disabled={isBusy}>
          {isBusy ? "Creating..." : "Create Mirror Template"}
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <div>{status}</div>
      </PanelSectionRow>
    </PanelSection>
  );
}

export default definePlugin(() => {
  return {
    name: "Mirror Controls",
    titleView: <div className={staticClasses.Title}>Mirror Controls</div>,
    content: <Content />,
    icon: <FaExchangeAlt />,
  };
});
