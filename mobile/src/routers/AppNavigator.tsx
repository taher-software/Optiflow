import { createNativeStackNavigator } from "@react-navigation/native-stack";

import type { RootStackParamList } from "../constants/routes";
import { HomeScreen } from "../screens/HomeScreen";
import { ProspectScreen } from "../screens/ProspectScreen";
import { SecurityCodeScreen } from "../screens/SecurityCodeScreen";

const Stack = createNativeStackNavigator<RootStackParamList>();

/** Root navigation stack: Prospect → SecurityCode → Home. */
export function AppNavigator() {
  return (
    <Stack.Navigator
      initialRouteName="Prospect"
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: "#020617" },
      }}
    >
      <Stack.Screen name="Prospect" component={ProspectScreen} />
      <Stack.Screen name="SecurityCode" component={SecurityCodeScreen} />
      <Stack.Screen name="Home" component={HomeScreen} />
    </Stack.Navigator>
  );
}

export default AppNavigator;
