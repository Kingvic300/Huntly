cask "huntly" do
  arch arm: "aarch64", intel: "x64"

  version "0.5.0"
  sha256 arm:   "f7230df4de7570c27f401d7c716e26d02168d34b6710f372770e4fb280c792be",
         intel: "b7e71ecb17ddc33743c87e918e030ec7c9fde13474a9aa8d5bd0a4ee2981ea3d"

  url "https://github.com/Kingvic300/Huntly/releases/download/v#{version}/Huntly_#{version}_#{arch}.dmg"
  name "Huntly"
  desc "Private, local job-hunting assistant"
  homepage "https://kingvic300.github.io/Huntly/"

  livecheck do
    url :url
    strategy :github_latest
  end

  auto_updates true
  depends_on macos: ">= :catalina"

  app "Huntly.app"

  zap trash: "~/Library/Application Support/huntly"

  caveats <<~EOS
    Huntly is not code-signed yet. If macOS says it cannot be opened, run:
      xattr -dr com.apple.quarantine "#{appdir}/Huntly.app"
  EOS
end
