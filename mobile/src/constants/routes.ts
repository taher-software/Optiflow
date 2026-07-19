/** Navigation route names + typed params for the root stack. */
export type RootStackParamList = {
  Prospect: undefined;
  SecurityCode: undefined;
  Home: undefined;
};

export const ROUTES = {
  prospect: "Prospect",
  securityCode: "SecurityCode",
  home: "Home",
} as const;

/** Persistent-storage key for the cached device id. */
export const DEVICE_ID_KEY = "optiflow.device_id";
