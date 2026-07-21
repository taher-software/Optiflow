import type { DownTimeStatus } from "./downtime";

/** Navigation route names + typed params for the root stack. */
export type RootStackParamList = {
  Prospect: undefined;
  SecurityCode: undefined;
  Home: undefined;
  IssueList: { status: DownTimeStatus };
  IssueDetail: { id: string };
  DeclareDownTime: undefined;
};

export const ROUTES = {
  prospect: "Prospect",
  securityCode: "SecurityCode",
  home: "Home",
  issueList: "IssueList",
  issueDetail: "IssueDetail",
  declareDownTime: "DeclareDownTime",
} as const;

/** Persistent-storage key for the cached device id. */
export const DEVICE_ID_KEY = "optiflow.device_id";
