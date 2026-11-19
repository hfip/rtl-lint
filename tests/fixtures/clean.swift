import UIKit

final class CleanView: UIView {
    private let titleLabel = UILabel()

    func setup() {
        titleLabel.textAlignment = .leading
        titleLabel.leadingAnchor.constraint(equalTo: leadingAnchor).isActive = true
    }
}
