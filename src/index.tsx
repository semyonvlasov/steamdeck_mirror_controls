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
  requested_app_id?: number;
  source_app_id?: number;
  source_path?: string;
  output_path?: string;
  swapped_tokens?: number;
};

const createMirrorTemplateCall = callable<
  [
    app_id: number,
    mirror_dpad: boolean,
    mirror_touchpads: boolean,
    mirror_sticks: boolean,
    mirror_menu_position: boolean,
    mirror_gyro_buttons: boolean
  ],
  MirrorResult
>("create_mirror_template");

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
  const [mirrorSticks, setMirrorSticks] = useState<boolean>(true);
  const [mirrorMenuPosition, setMirrorMenuPosition] = useState<boolean>(true);
  const [mirrorGyroButtons, setMirrorGyroButtons] = useState<boolean>(true);
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
      const result = await createMirrorTemplateCall(
        appId ?? 0,
        mirrorDpad,
        mirrorTouchpads,
        mirrorSticks,
        mirrorMenuPosition,
        mirrorGyroButtons
      );
      if (!result?.ok) {
        setStatus(result?.error ?? "Failed to create mirror template");
        return;
      }

      const appText = result.app_id ? `App ${result.app_id}` : "Current app";
      const requestText =
        typeof result.requested_app_id === "number"
          ? `requested ${result.requested_app_id}`
          : "requested ?";
      const sourceText =
        typeof result.source_app_id === "number" && result.source_app_id > 0
          ? `source ${result.source_app_id}`
          : "source ?";
      const swapsText = Number(result.swapped_tokens ?? 0);
      const nextStatus = `${appText}: saved (${swapsText} swaps, ${requestText}, ${sourceText})`;
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
        <ToggleField
          label="Mirror Menu Position"
          checked={mirrorMenuPosition}
          onChange={(value: boolean) => setMirrorMenuPosition(value)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ToggleField
          label="Mirror Gyro Buttons"
          checked={mirrorGyroButtons}
          onChange={(value: boolean) => setMirrorGyroButtons(value)}
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
