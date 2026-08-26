const { withDangerousMod } = require("@expo/config-plugins");
const fs = require("fs");
const path = require("path");

module.exports = function withAdiRegistration(config) {
    return withDangerousMod(config, [
        "android",
        async (config) => {
            const source = path.join(
                config.modRequest.projectRoot,
                "assets",
                "adi-registration.properties"
            );

            const destinationDir = path.join(
                config.modRequest.platformProjectRoot,
                "app",
                "src",
                "main",
                "assets"
            );

            const destination = path.join(
                destinationDir,
                "adi-registration.properties"
            );

            fs.mkdirSync(destinationDir, { recursive: true });
            fs.copyFileSync(source, destination);

            return config;
        },
    ]);
};