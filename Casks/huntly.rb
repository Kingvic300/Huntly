cask "huntly" do
  arch arm: "aarch64", intel: "x64"

  version "0.3.3"
  sha256 arm:   "e5ebba8621abfe7d152b0fcdacb4a9ce90b4b15eb41f317a326398238f8ee906",
         intel: "dcb7fb943468c3020aec9e028f0e45782e095d01e4925349d3c6815aea056471"

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
